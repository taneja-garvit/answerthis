"""DOI → paper metadata, through the shared PaperCache.

Order: per-run memo → paper_cache (fresh) → Crossref and OpenAlex in parallel →
merge → write cache. Provider outages are not cached, so a later run retries;
"not found" is cached briefly so a bad DOI is not looked up on every run."""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models import PaperCache
from app.papers.base import PaperProvider, PaperProviderError, PaperRecord
from app.services.segmentation import ReferenceEntry

logger = logging.getLogger(__name__)

NOT_FOUND_MARKER = "not_found"
NEGATIVE_CACHE_TTL = timedelta(days=1)


class LookupStatus(StrEnum):
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"  # no provider knows this DOI
    UNAVAILABLE = "UNAVAILABLE"  # providers failed (timeout, rate limit, outage)


@dataclass(frozen=True)
class PaperLookup:
    status: LookupStatus
    paper: PaperRecord | None = None
    from_cache: bool = False
    errors: tuple[str, ...] = ()


def merge_records(doi: str, records: list[PaperRecord]) -> PaperRecord:
    """Crossref is preferred for bibliographic fields and structured abstracts;
    OpenAlex fills gaps and is the source of open-access information."""
    by_name = {r.providers[0]: r for r in records if r.providers}
    ordered = [by_name[n] for n in ("crossref", "openalex") if n in by_name] or records

    def first(attr: str):
        return next((getattr(r, attr) for r in ordered if getattr(r, attr)), None)

    with_abstract = next((r for r in ordered if r.abstract), None)
    openalex = by_name.get("openalex")
    return PaperRecord(
        doi=doi,
        title=first("title"),
        authors=first("authors") or [],
        journal=first("journal"),
        publisher=first("publisher"),
        publication_year=first("publication_year"),
        abstract=with_abstract.abstract if with_abstract else None,
        abstract_sections=with_abstract.abstract_sections if with_abstract else [],
        abstract_source=with_abstract.abstract_source if with_abstract else None,
        license=first("license"),
        open_access=openalex.open_access if openalex else ordered[0].open_access,
        openalex_id=first("openalex_id"),
        providers=[n for r in ordered for n in r.providers],
    )


class PaperResolver:
    def __init__(self, providers: list[PaperProvider], *, cache_ttl_days: int) -> None:
        self._providers = providers
        self._ttl = timedelta(days=cache_ttl_days)
        self._memo: dict[str, PaperLookup] = {}

    async def lookup(
        self, session: AsyncSession, doi: str, *, refresh: bool = False
    ) -> PaperLookup:
        if doi in self._memo:
            return self._memo[doi]
        result = None if refresh else await self._from_cache(session, doi)
        if result is None:
            result = await self._fetch(session, doi)
        self._memo[doi] = result
        return result

    async def _from_cache(self, session: AsyncSession, doi: str) -> PaperLookup | None:
        row = await session.scalar(select(PaperCache).where(PaperCache.doi == doi))
        if row is None:
            return None
        age = utcnow() - row.fetched_at
        if row.last_error == NOT_FOUND_MARKER and not row.normalized:
            return (
                PaperLookup(LookupStatus.NOT_FOUND, from_cache=True)
                if age < NEGATIVE_CACHE_TTL
                else None
            )
        if age >= self._ttl or not row.normalized:
            return None
        return PaperLookup(
            LookupStatus.FOUND, PaperRecord.model_validate({**row.normalized, "doi": doi}), True
        )

    async def _fetch(self, session: AsyncSession, doi: str) -> PaperLookup:
        results = await asyncio.gather(
            *(p.get_by_doi(doi) for p in self._providers), return_exceptions=True
        )
        records: list[PaperRecord] = []
        errors: list[str] = []
        for provider, outcome in zip(self._providers, results, strict=True):
            if isinstance(outcome, PaperProviderError):
                errors.append(f"{outcome.provider}:{outcome.kind}")
            elif isinstance(outcome, BaseException):
                logger.error(
                    "paper provider crashed",
                    extra={"provider": provider.name, "exc_class": type(outcome).__name__},
                )
                errors.append(f"{provider.name}:error")
            elif outcome is not None:
                records.append(outcome)

        if records:
            paper = merge_records(doi, records)
            await self._store(
                session,
                doi,
                paper.model_dump(mode="json"),
                paper.providers,
                "; ".join(errors) or None,
            )
            return PaperLookup(LookupStatus.FOUND, paper, errors=tuple(errors))
        if errors:
            return PaperLookup(LookupStatus.UNAVAILABLE, errors=tuple(errors))
        await self._store(session, doi, {}, [], NOT_FOUND_MARKER)
        return PaperLookup(LookupStatus.NOT_FOUND)

    async def _store(
        self,
        session: AsyncSession,
        doi: str,
        normalized: dict,
        providers: list[str],
        error: str | None,
    ) -> None:
        now = utcnow()
        statement = insert(PaperCache).values(
            doi=doi,
            normalized=normalized,
            raw={},
            providers=providers,
            fetched_at=now,
            last_error=error,
        )
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[PaperCache.doi],
                set_={
                    "normalized": statement.excluded.normalized,
                    "providers": statement.excluded.providers,
                    "fetched_at": statement.excluded.fetched_at,
                    "last_error": statement.excluded.last_error,
                    "updated_at": now,
                },
            )
        )


_WORD = re.compile(r"[a-z0-9]+")


def reference_title_match(reference: ReferenceEntry | None, paper: PaperRecord) -> float | None:
    """Share of the resolved title's words that appear in the draft's reference
    entry. None when there is nothing to compare (e.g. the entry is only a DOI)."""
    if reference is None or not paper.title:
        return None
    title_words = {w for w in _WORD.findall(paper.title.lower()) if len(w) > 3}
    entry_words = set(_WORD.findall(reference.text.lower()))
    if not title_words or len(entry_words) < 5:
        return None
    return round(len(title_words & entry_words) / len(title_words), 2)


@dataclass
class CitationResolution:
    """How each citation of one claim resolved."""

    label: str
    doi: str | None
    lookup: PaperLookup | None
    reference: ReferenceEntry | None = None
    title_match: float | None = None
    problems: list[str] = field(default_factory=list)

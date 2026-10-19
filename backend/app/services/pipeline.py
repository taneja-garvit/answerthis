"""Draft → claims → citations → sources → evidence → assessment, persisted.

Execution is synchronous for the MVP, but each stage is its own function with
explicit inputs, so this orchestration can move behind a job queue later
without changing extraction, resolution, retrieval or assessment.

Re-run semantics (POST /api/drafts/{id}/analyze):
- mode "resume" (default): claims are extracted only if the draft has none.
  Claims that already have an assessment and status READY are reused untouched
  (no LLM calls); claims that are PENDING/ERROR or unassessed are processed.
- mode "reextract": deletes and re-extracts the draft's claims, but only when
  no claim has a human review yet (otherwise 409), so decisions are never lost.
A draft can only be analyzed by one request at a time (409 otherwise).

Commits happen after each stage and each claim, so earlier claims persist if a
later one fails, and no transaction is held open while waiting on the LLM."""

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Literal

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import LLMAuthError, LLMError, LLMProvider, LLMRateLimitError
from app.api.errors import AppError, ConflictError, NotFoundError
from app.core.config import Settings
from app.db.base import utcnow
from app.domain.enums import (
    AccessLevel,
    ClaimStatus,
    DraftAnalysisStatus,
    IssueType,
    SourceAccessStatus,
    Verdict,
)
from app.models import Assessment, Claim, ClaimSource, Draft, Evidence, Source
from app.papers.base import PaperProvider, PaperRecord
from app.repositories import claims as claims_repo
from app.schemas.analysis import AnalysisResponse
from app.schemas.claim import ClaimReviewResponse, Issue
from app.services.citation_resolution import (
    CitationResolution,
    LookupStatus,
    PaperResolver,
    reference_title_match,
)
from app.services.citations import marker_label, parse_citations
from app.services.claim_assessment import (
    AssessmentResult,
    EvidenceInput,
    SourceInput,
    assess_claim,
    rule_unverifiable,
)
from app.services.claim_extraction import extract_claims
from app.services.claims import latest_assessment, to_claim_review_response
from app.services.evidence_retrieval import EvidenceRetriever, SourceDocument
from app.services.segmentation import ParsedDraft, ReferenceEntry, parse_draft

logger = logging.getLogger(__name__)

STALE_LOCK = timedelta(minutes=15)
TITLE_MISMATCH_THRESHOLD = 0.3


class TransientSourceError(AppError):
    """Metadata providers were unreachable; the claim can be retried later."""

    status_code = 503
    code = "metadata_providers_unavailable"


@dataclass
class AnalyzeOptions:
    mode: Literal["resume", "reextract"] = "resume"
    citations: dict[str, str] = field(default_factory=dict)  # "1" -> DOI, overrides references
    refresh_metadata: bool = False


@dataclass
class _Run:
    parsed: ParsedDraft
    references: dict[str, ReferenceEntry]
    overrides: dict[str, str]
    resolver: PaperResolver
    refresh: bool
    llm_calls: int = 0


class PipelineService:
    def __init__(
        self,
        *,
        llm: LLMProvider,
        paper_providers: list[PaperProvider],
        retriever: EvidenceRetriever,
        settings: Settings,
    ) -> None:
        self.llm = llm
        self.paper_providers = paper_providers
        self.retriever = retriever
        self.settings = settings

    # ------------------------------------------------------------------ draft

    async def analyze_draft(
        self, session: AsyncSession, draft_id: uuid.UUID, options: AnalyzeOptions
    ) -> AnalysisResponse:
        previous_status = await self._acquire(session, draft_id)
        started = time.perf_counter()
        try:
            draft = await session.get(Draft, draft_id)
            assert draft is not None
            # Plain values: ORM objects are expired by the rollbacks below.
            project_id = draft.project_id
            run = self._new_run(draft, options)
            claims = list(await claims_repo.list_claims_for_draft(session, draft_id))

            if options.mode == "reextract" and claims:
                if any(c.review is not None for c in claims):
                    raise ConflictError(
                        "Claims of this draft already have human reviews; re-extraction would "
                        "discard them. Use mode 'resume', or reassess individual claims.",
                        code="reviews_exist",
                    )
                await session.execute(delete(Claim).where(Claim.draft_id == draft_id))
                await session.commit()
                claims = []

            rerun = bool(claims)
            if not claims:
                claims = await self._extract(session, draft, run)

            to_process = [
                c.id for c in claims if c.status != ClaimStatus.READY or not c.assessments
            ]
            total_claims = len(claims)
            stop: LLMError | None = None
            for claim_id in to_process:
                if stop is not None:
                    await self._mark_failed(session, claim_id, f"Skipped: {stop}")
                    continue
                claim = await claims_repo.get_claim(session, claim_id, populate_existing=True)
                assert claim is not None
                try:
                    await self._process_claim(session, project_id, claim, run)
                except (LLMRateLimitError, LLMAuthError) as exc:
                    # Further calls would fail the same way and burn quota.
                    stop = exc
                    await self._mark_failed(session, claim_id, str(exc))
                except (LLMError, TransientSourceError) as exc:
                    await self._mark_failed(session, claim_id, str(exc))

            await self._release(session, draft_id, DraftAnalysisStatus.ANALYZED, analyzed=True)
        except ConflictError:
            await self._release(session, draft_id, previous_status)
            raise
        except Exception:
            await self._release(session, draft_id, DraftAnalysisStatus.FAILED)
            raise

        logger.info(
            "analysis complete",
            extra={
                "draft_id": str(draft_id),
                "project_id": str(project_id),
                "claims": total_claims,
                "processed": len(to_process),
                "llm_calls": run.llm_calls,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        fresh = await claims_repo.list_claims_for_draft(session, draft_id, populate_existing=True)
        responses = [to_claim_review_response(c) for c in fresh]
        return AnalysisResponse(
            draft_id=draft_id,
            project_id=project_id,
            analysis_status=DraftAnalysisStatus.ANALYZED,
            rerun=rerun,
            claims_extracted=len(responses),
            claims_processed=len(to_process),
            claims_reused=len(responses) - len(to_process),
            claims_assessed=sum(1 for r in responses if r.assessment is not None),
            claims_unverifiable=sum(
                1
                for r in responses
                if r.assessment and r.assessment.verdict == Verdict.UNVERIFIABLE
            ),
            claims_failed=sum(1 for r in responses if r.status == ClaimStatus.ERROR),
            llm_provider=self.llm.name,
            llm_model=self.llm.model,
            llm_calls=run.llm_calls,
            claims=responses,
        )

    async def _acquire(self, session: AsyncSession, draft_id: uuid.UUID) -> DraftAnalysisStatus:
        current = await session.scalar(select(Draft.analysis_status).where(Draft.id == draft_id))
        if current is None:
            raise NotFoundError("Draft not found")
        now = utcnow()
        locked = await session.execute(
            update(Draft)
            .where(
                Draft.id == draft_id,
                or_(
                    Draft.analysis_status != DraftAnalysisStatus.ANALYZING,
                    Draft.analysis_started_at < now - STALE_LOCK,
                ),
            )
            .values(analysis_status=DraftAnalysisStatus.ANALYZING, analysis_started_at=now)
            .returning(Draft.id)
            .execution_options(synchronize_session=False)
        )
        if locked.scalar_one_or_none() is None:
            await session.rollback()
            raise ConflictError(
                "This draft is already being analyzed.", code="analysis_in_progress"
            )
        await session.commit()
        return DraftAnalysisStatus(current)

    async def _release(
        self,
        session: AsyncSession,
        draft_id: uuid.UUID,
        status: DraftAnalysisStatus,
        *,
        analyzed: bool = False,
    ) -> None:
        await session.rollback()
        values: dict = {"analysis_status": status}
        if analyzed:
            values["analyzed_at"] = utcnow()
        await session.execute(
            update(Draft)
            .where(Draft.id == draft_id)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        await session.commit()

    def _new_run(self, draft: Draft, options: AnalyzeOptions) -> _Run:
        parsed = parse_draft(draft.original_text)
        return _Run(
            parsed=parsed,
            references=parsed.references,
            overrides=options.citations,
            resolver=PaperResolver(
                self.paper_providers, cache_ttl_days=self.settings.paper_cache_ttl_days
            ),
            refresh=options.refresh_metadata,
        )

    async def _extract(self, session: AsyncSession, draft: Draft, run: _Run) -> list[Claim]:
        extraction = await extract_claims(
            run.parsed, self.llm, max_retries=self.settings.llm_max_retries
        )
        run.llm_calls += extraction.llm_calls
        for position, item in enumerate(extraction.claims, start=1):
            session.add(
                Claim(
                    draft_id=draft.id,
                    position=position,
                    claim_text=item.claim_text,
                    original_sentence=item.sentence.text,
                    citation_marker=marker_label(item.citations),
                    status=ClaimStatus.PENDING,
                )
            )
        await session.commit()
        return list(await claims_repo.list_claims_for_draft(session, draft.id))

    async def _mark_failed(self, session: AsyncSession, claim_id: uuid.UUID, message: str) -> None:
        await session.rollback()
        claim = await session.get(Claim, claim_id, populate_existing=True)
        assert claim is not None
        has_assessment = await session.scalar(
            select(Assessment.id).where(Assessment.claim_id == claim_id).limit(1)
        )
        # A failed re-run never hides an earlier successful assessment.
        claim.status = ClaimStatus.READY if has_assessment else ClaimStatus.ERROR
        claim.processing_error = message[:500]
        await session.commit()
        logger.warning(
            "claim processing failed", extra={"claim_id": str(claim_id), "reason": message[:200]}
        )

    # ------------------------------------------------------------------ claim

    async def reassess_claim(
        self, session: AsyncSession, claim_id: uuid.UUID, *, refresh_metadata: bool = False
    ) -> ClaimReviewResponse:
        claim = await claims_repo.get_claim(session, claim_id)
        if claim is None:
            raise NotFoundError("Claim not found")
        draft = claim.draft
        run = self._new_run(draft, AnalyzeOptions(refresh_metadata=refresh_metadata))
        try:
            await self._process_claim(session, draft.project_id, claim, run)
        except (LLMError, TransientSourceError) as exc:
            await self._mark_failed(session, claim_id, f"Latest reassessment failed: {exc}")
            raise
        refreshed = await claims_repo.get_claim(session, claim_id, populate_existing=True)
        assert refreshed is not None
        return to_claim_review_response(refreshed)

    async def _process_claim(
        self, session: AsyncSession, project_id: uuid.UUID, claim: Claim, run: _Run
    ) -> None:
        stage_started = time.perf_counter()
        resolutions = await self._resolve(session, claim, run)
        found = [r for r in resolutions if r.lookup and r.lookup.status == LookupStatus.FOUND]
        if not found and any(
            r.lookup and r.lookup.status == LookupStatus.UNAVAILABLE for r in resolutions
        ):
            errors = sorted({e for r in resolutions if r.lookup for e in r.lookup.errors})
            raise TransientSourceError(
                "Paper metadata providers were unavailable (" + ", ".join(errors) + "). "
                "Re-run the analysis to retry."
            )

        sources = [await self._upsert_source(session, project_id, r) for r in found]
        await session.execute(delete(ClaimSource).where(ClaimSource.claim_id == claim.id))
        for position, (resolution, source) in enumerate(zip(found, sources, strict=True)):
            session.add(
                ClaimSource(
                    claim_id=claim.id,
                    source_id=source.id,
                    position=position,
                    citation_marker=resolution.label,
                )
            )

        documents = [d for d in (self._document(s) for s in sources) if d is not None]
        candidates = self.retriever.retrieve(claim.claim_text, documents) if documents else []
        evidence_rows = await self._store_evidence(session, claim, candidates)
        await session.commit()  # release the transaction before any LLM call

        rule = self._rule_outcome(resolutions, found, sources, documents, candidates)
        extra_issues = self._extra_issues(resolutions, found)
        if rule is not None:
            result = rule
            result.issues.extend(i for i in extra_issues if i.type != result.issues[0].type)
        else:
            labels = {s.id: r.label for r, s in zip(found, sources, strict=True)}
            result = await assess_claim(
                self.llm,
                claim_text=claim.claim_text,
                original_sentence=claim.original_sentence,
                sources=[
                    SourceInput(
                        label=labels[s.id],
                        doi=s.doi,
                        title=s.title,
                        journal=s.journal,
                        year=s.publication_year,
                        access="abstract only" if s.abstract else "no text available",
                    )
                    for s in sources
                ],
                evidence=[
                    EvidenceInput(
                        label=f"E{i}",
                        evidence_id=row.id,
                        source_label=labels[row.source_id],
                        location=row.location,
                        access_level=row.access_level,
                        passage=row.passage,
                    )
                    for i, row in enumerate(evidence_rows, start=1)
                ],
                max_retries=self.settings.llm_max_retries,
                extra_issues=extra_issues,
            )
            run.llm_calls += result.llm_calls
        await self._store_assessment(session, claim, result)
        logger.info(
            "claim assessed",
            extra={
                "claim_id": str(claim.id),
                "verdict": result.verdict.value,
                "provider": result.provider,
                "evidence": len(evidence_rows),
                "duration_ms": round((time.perf_counter() - stage_started) * 1000, 1),
            },
        )

    async def _resolve(
        self, session: AsyncSession, claim: Claim, run: _Run
    ) -> list[CitationResolution]:
        resolutions: list[CitationResolution] = []
        for ref in parse_citations(claim.original_sentence):
            reference = run.references.get(ref.value) if ref.kind == "number" else None
            label = f"[{ref.value}]" if ref.kind == "number" else ref.value
            if ref.kind == "number":
                doi = run.overrides.get(ref.value) or (reference.doi if reference else None)
            else:
                doi = ref.value
            if doi is None:
                resolutions.append(CitationResolution(label, None, None, reference))
                continue
            lookup = await run.resolver.lookup(session, doi, refresh=run.refresh)
            resolution = CitationResolution(label, doi, lookup, reference)
            if lookup.paper is not None and ref.value not in run.overrides:
                resolution.title_match = reference_title_match(reference, lookup.paper)
            resolutions.append(resolution)
        return resolutions

    async def _upsert_source(
        self, session: AsyncSession, project_id: uuid.UUID, resolution: CitationResolution
    ) -> Source:
        paper: PaperRecord = resolution.lookup.paper  # type: ignore[union-attr]
        source = await session.scalar(
            select(Source).where(Source.project_id == project_id, Source.doi == paper.doi)
        )
        if source is None:
            source = Source(project_id=project_id, doi=paper.doi)
            session.add(source)
        source.title = paper.title or f"DOI {paper.doi}"
        source.authors = paper.authors
        source.journal = paper.journal
        source.publication_year = paper.publication_year
        source.abstract = paper.abstract
        source.open_access_url = paper.open_access.oa_url
        # Only abstracts are ingested; open-access full text is linked, not fetched.
        source.access_status = (
            SourceAccessStatus.ABSTRACT_ONLY if paper.abstract else SourceAccessStatus.UNAVAILABLE
        )
        source.source_metadata = {
            "publisher": paper.publisher,
            "license": paper.license,
            "open_access": paper.open_access.model_dump(),
            "openalex_id": paper.openalex_id,
            "providers": paper.providers,
            "abstract_source": paper.abstract_source,
            "abstract_sections": [s.model_dump() for s in paper.abstract_sections],
            "reference_text": resolution.reference.text if resolution.reference else None,
            "reference_title_match": resolution.title_match,
            "resolved_at": utcnow().isoformat(),
        }
        await session.flush()
        return source

    @staticmethod
    def _document(source: Source) -> SourceDocument | None:
        if not source.abstract:
            return None
        sections = source.source_metadata.get("abstract_sections") or []
        via = (
            " (via OpenAlex)" if source.source_metadata.get("abstract_source") == "openalex" else ""
        )
        located = [
            (f"Abstract — {s['title']}" if s.get("title") else f"Abstract{via}", s["text"])
            for s in sections
            if s.get("text")
        ] or [(f"Abstract{via}", source.abstract)]
        return SourceDocument(source.id, AccessLevel.ABSTRACT, located)

    async def _store_evidence(
        self, session: AsyncSession, claim: Claim, candidates
    ) -> list[Evidence]:
        existing = list(
            (await session.execute(select(Evidence).where(Evidence.claim_id == claim.id))).scalars()
        )
        by_key = {(e.source_id, e.passage, e.location): e for e in existing}
        for row in existing:
            row.is_current = False
        rows: list[Evidence] = []
        for candidate in candidates:
            row = by_key.get((candidate.source_id, candidate.passage, candidate.location))
            if row is None:
                row = Evidence(
                    claim_id=claim.id,
                    source_id=candidate.source_id,
                    passage=candidate.passage,
                    location=candidate.location,
                    access_level=candidate.access_level,
                )
                session.add(row)
            row.retrieval_method = candidate.retrieval_method
            row.retrieval_score = candidate.retrieval_score
            row.rank = candidate.rank
            row.is_current = True
            rows.append(row)
        await session.flush()
        return rows

    @staticmethod
    def _rule_outcome(
        resolutions, found, sources, documents, candidates
    ) -> AssessmentResult | None:
        if not resolutions:
            return rule_unverifiable(
                IssueType.EVIDENCE_UNAVAILABLE, "No citation is attached to this claim."
            )
        if not found:
            missing = [
                r for r in resolutions if r.lookup and r.lookup.status == LookupStatus.NOT_FOUND
            ]
            if missing:
                return rule_unverifiable(
                    IssueType.SOURCE_MISMATCH,
                    "The cited DOI could not be found in Crossref or OpenAlex ("
                    + ", ".join(r.doi for r in missing)
                    + ").",
                )
            labels = ", ".join(r.label for r in resolutions)
            return rule_unverifiable(
                IssueType.EVIDENCE_UNAVAILABLE,
                f"Citation {labels} could not be matched to a reference with a DOI.",
            )
        if not documents:
            return rule_unverifiable(
                IssueType.EVIDENCE_UNAVAILABLE,
                "No public abstract is available for the cited source, and no open-access "
                "text has been ingested.",
            )
        if not candidates:
            return rule_unverifiable(
                IssueType.INSUFFICIENT_EVIDENCE,
                "No passage in the available text of the cited source addresses this claim.",
            )
        return None

    @staticmethod
    def _extra_issues(resolutions, found) -> list[Issue]:
        issues: list[Issue] = []
        for r in found:
            if r.title_match is not None and r.title_match < TITLE_MISMATCH_THRESHOLD:
                issues.append(
                    Issue(
                        type=IssueType.SOURCE_MISMATCH,
                        description=(
                            f"The draft's reference entry for {r.label} does not match the "
                            "title of the paper its DOI resolves to "
                            f"(overlap {r.title_match:.0%}). The DOI may be wrong."
                        ),
                    )
                )
        if found:
            unresolved = [r.label for r in resolutions if r not in found]
            if unresolved:
                issues.append(
                    Issue(
                        type=IssueType.EVIDENCE_UNAVAILABLE,
                        description="Citation " + ", ".join(unresolved) + " could not be resolved; "
                        "only the other cited source(s) were checked.",
                    )
                )
        return issues

    async def _store_assessment(
        self, session: AsyncSession, claim: Claim, result: AssessmentResult
    ) -> None:
        session.add(
            Assessment(
                claim_id=claim.id,
                verdict=result.verdict,
                confidence_level=result.confidence_level,
                confidence=None,
                issues=[i.model_dump(mode="json") for i in result.issues],
                explanation=result.explanation,
                suggested_revision=result.suggested_revision,
                evidence_ids=[str(i) for i in result.evidence_ids],
                provider=result.provider,
                model=result.model,
                prompt_version=result.prompt_version,
                generation_metadata=result.generation_metadata,
            )
        )
        row = await session.get(Claim, claim.id)
        assert row is not None
        row.status = ClaimStatus.READY
        row.processing_error = None
        await session.commit()


__all__ = ["AnalyzeOptions", "PipelineService", "TransientSourceError", "latest_assessment"]

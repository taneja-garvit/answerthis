"""OpenAlex API: metadata, open-access status/location, and abstracts (stored by
OpenAlex as an inverted index)."""

from urllib.parse import quote

import httpx
from pydantic import SecretStr

from app.papers.base import AbstractSection, OpenAccessInfo, PaperRecord
from app.papers.http import Sleep, get_json


def reconstruct_abstract(inverted: dict[str, list[int]] | None) -> str | None:
    if not inverted:
        return None
    positions = {pos: word for word, places in inverted.items() for pos in places}
    return " ".join(positions[i] for i in sorted(positions)) or None


def parse_openalex(doi: str, work: dict) -> PaperRecord:
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    oa = work.get("open_access") or {}
    best = work.get("best_oa_location") or {}
    source = (work.get("primary_location") or {}).get("source") or {}
    authors = []
    for authorship in work.get("authorships") or []:
        author = authorship.get("author") or {}
        authors.append({"name": author.get("display_name"), "orcid": author.get("orcid")})
    return PaperRecord(
        doi=doi,
        title=work.get("title") or work.get("display_name"),
        authors=authors,
        journal=source.get("display_name"),
        publication_year=work.get("publication_year"),
        abstract=abstract,
        abstract_sections=[AbstractSection(text=abstract)] if abstract else [],
        abstract_source="openalex" if abstract else None,
        open_access=OpenAccessInfo(
            is_oa=oa.get("is_oa"),
            oa_status=oa.get("oa_status"),
            oa_url=oa.get("oa_url") or best.get("pdf_url") or best.get("landing_page_url"),
            landing_page_url=best.get("landing_page_url"),
        ),
        license={"name": best.get("license")} if best.get("license") else None,
        openalex_id=work.get("id"),
        providers=["openalex"],
    )


class OpenAlexProvider:
    name = "openalex"

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        contact_email: str | None,
        api_key: SecretStr | None,
        timeout: float,
        max_retries: int,
        base_url: str = "https://api.openalex.org",
        sleep: Sleep | None = None,
    ) -> None:
        self._client = client
        self._contact = contact_email
        self._api_key = api_key
        self._timeout = timeout
        self._max_retries = max_retries
        self._base = base_url.rstrip("/")
        self._sleep = sleep

    async def get_by_doi(self, doi: str) -> PaperRecord | None:
        params: dict[str, str] = {}
        if self._contact:
            params["mailto"] = self._contact
        if self._api_key:
            params["api_key"] = self._api_key.get_secret_value()
        kwargs = {"sleep": self._sleep} if self._sleep else {}
        data = await get_json(
            self._client,
            self.name,
            f"{self._base}/works/https://doi.org/{quote(doi, safe='/()')}",
            params=params or None,
            request_timeout=self._timeout,
            max_retries=self._max_retries,
            **kwargs,
        )
        return parse_openalex(doi, data) if data else None

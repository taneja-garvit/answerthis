"""Crossref REST API: bibliographic metadata and (when deposited) the abstract."""

import html
import re
from urllib.parse import quote

import httpx

from app.papers.base import AbstractSection, PaperRecord
from app.papers.http import Sleep, get_json

_SECTION = re.compile(
    r"<jats:sec[^>]*>\s*(?:<jats:title[^>]*>(.*?)</jats:title>)?\s*(.*?)</jats:sec>", re.S
)
_TAG = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    # Crossref double-escapes some entities ("&amp;lt;").
    text = html.unescape(html.unescape(_TAG.sub(" ", text)))
    # Collapse runs and line breaks but keep single typographic spaces (e.g. thin spaces).
    text = re.sub(
        r"\s+", lambda m: " " if "\n" in m.group(0) or len(m.group(0)) > 1 else m.group(0), text
    )
    return text.strip()


def parse_jats_abstract(raw: str | None) -> list[AbstractSection]:
    if not raw:
        return []
    sections = [
        AbstractSection(title=_clean(title) or None, text=_clean(body))
        for title, body in _SECTION.findall(raw)
        if _clean(body)
    ]
    if sections:
        return sections
    body = re.sub(r"^\s*<jats:title[^>]*>\s*Abstract\s*</jats:title>", "", raw, flags=re.I)
    text = _clean(body)
    return [AbstractSection(text=text)] if text else []


def parse_crossref(doi: str, message: dict) -> PaperRecord:
    sections = parse_jats_abstract(message.get("abstract"))
    year = None
    for key in ("published", "published-online", "published-print", "issued"):
        parts = (message.get(key) or {}).get("date-parts") or [[None]]
        if parts and parts[0] and parts[0][0]:
            year = int(parts[0][0])
            break
    licences = message.get("license") or []
    return PaperRecord(
        doi=doi,
        title=(message.get("title") or [None])[0],
        authors=[
            {
                "given": a.get("given"),
                "family": a.get("family") or a.get("name"),
                "orcid": a.get("ORCID"),
            }
            for a in message.get("author") or []
        ],
        journal=(message.get("container-title") or [None])[0],
        publisher=message.get("publisher"),
        publication_year=year,
        abstract=" ".join(s.text for s in sections) or None,
        abstract_sections=sections,
        abstract_source="crossref" if sections else None,
        license={"url": licences[0].get("URL")} if licences else None,
        providers=["crossref"],
    )


class CrossrefProvider:
    name = "crossref"

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        contact_email: str | None,
        timeout: float,
        max_retries: int,
        base_url: str = "https://api.crossref.org",
        sleep: Sleep | None = None,
    ) -> None:
        self._client = client
        self._contact = contact_email
        self._timeout = timeout
        self._max_retries = max_retries
        self._base = base_url.rstrip("/")
        self._sleep = sleep

    async def get_by_doi(self, doi: str) -> PaperRecord | None:
        params = {"mailto": self._contact} if self._contact else None
        kwargs = {"sleep": self._sleep} if self._sleep else {}
        data = await get_json(
            self._client,
            self.name,
            f"{self._base}/works/{quote(doi, safe='/()')}",
            params=params,
            request_timeout=self._timeout,
            max_retries=self._max_retries,
            **kwargs,
        )
        if not data or "message" not in data:
            return None
        return parse_crossref(doi, data["message"])

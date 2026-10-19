"""Provider-neutral paper metadata model and provider interface."""

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class AbstractSection(BaseModel):
    title: str | None = None
    text: str


class OpenAccessInfo(BaseModel):
    is_oa: bool | None = None
    oa_status: str | None = None
    oa_url: str | None = None
    landing_page_url: str | None = None


class PaperRecord(BaseModel):
    """Normalized metadata. Also the JSON shape stored in paper_cache.normalized."""

    model_config = ConfigDict(extra="ignore")

    doi: str
    title: str | None = None
    authors: list[dict[str, Any]] = Field(default_factory=list)
    journal: str | None = None
    publisher: str | None = None
    publication_year: int | None = None
    abstract: str | None = None
    abstract_sections: list[AbstractSection] = Field(default_factory=list)
    abstract_source: str | None = None  # provider the abstract came from
    license: dict[str, Any] | None = None
    open_access: OpenAccessInfo = Field(default_factory=OpenAccessInfo)
    openalex_id: str | None = None
    providers: list[str] = Field(default_factory=list)

    def sections(self) -> list[AbstractSection]:
        if self.abstract_sections:
            return self.abstract_sections
        return [AbstractSection(text=self.abstract)] if self.abstract else []


class PaperProviderError(Exception):
    """A provider could not answer (as opposed to answering "not found")."""

    def __init__(
        self, provider: str, kind: Literal["timeout", "rate_limited", "unavailable", "bad_response"]
    ) -> None:
        super().__init__(f"{provider}: {kind}")
        self.provider = provider
        self.kind = kind


class PaperProvider(Protocol):
    name: str

    async def get_by_doi(self, doi: str) -> PaperRecord | None:
        """Metadata for a normalized DOI, None if the provider has no such work.
        Raises PaperProviderError on timeouts, rate limits or outages."""
        ...

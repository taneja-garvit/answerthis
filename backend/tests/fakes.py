"""Offline stand-ins for external services. No network access."""

import json
from collections.abc import Callable
from pathlib import Path

from app.ai.base import LLMRequest, LLMResponse
from app.papers.base import PaperProviderError, PaperRecord
from app.papers.crossref import parse_crossref
from app.papers.openalex import parse_openalex

FIXTURES = Path(__file__).parent / "fixtures"
HF_DOI = "10.1002/ejhf.3568"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakePaperProvider:
    """Serves records by DOI; can be told to fail. Records every lookup."""

    def __init__(self, name: str, records: dict[str, PaperRecord] | None = None) -> None:
        self.name = name
        self.records = records or {}
        self.failures: dict[str, str] = {}  # doi (or "*") -> PaperProviderError kind
        self.calls: list[str] = []

    async def get_by_doi(self, doi: str) -> PaperRecord | None:
        self.calls.append(doi)
        kind = self.failures.get(doi) or self.failures.get("*")
        if kind:
            raise PaperProviderError(self.name, kind)  # type: ignore[arg-type]
        return self.records.get(doi)

    @classmethod
    def crossref_heart_failure(cls) -> "FakePaperProvider":
        message = load_fixture("crossref_ejhf_3568.json")["message"]
        return cls("crossref", {HF_DOI: parse_crossref(HF_DOI, message)})

    @classmethod
    def openalex_heart_failure(cls) -> "FakePaperProvider":
        work = load_fixture("openalex_ejhf_3568.json")
        return cls("openalex", {HF_DOI: parse_openalex(HF_DOI, work)})


class ScriptedLLM:
    """LLM provider that answers with a function of the request (or raises)."""

    name = "scripted"

    def __init__(
        self, respond: Callable[[LLMRequest], dict | str | Exception], model: str = "scripted-1"
    ) -> None:
        self.model = model
        self._respond = respond
        self.requests: list[LLMRequest] = []

    async def complete_json(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        result = self._respond(request)
        if isinstance(result, Exception):
            raise result
        content = result if isinstance(result, str) else json.dumps(result)
        return LLMResponse(
            content=content, provider=self.name, model=self.model, usage={"total_tokens": 10}
        )

    async def aclose(self) -> None:
        return None

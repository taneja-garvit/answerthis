"""Offline provider for tests, local development without a key, and the seeded
demo. It never pretends to assess arbitrary claims:

- extraction: one claim per factual-looking sentence (no compound splitting);
- assessment: reproduces the seeded demo's hand-authored fixtures when the claim
  is a demo claim; otherwise returns UNVERIFIABLE and says no live assessment ran.
"""

import json
from typing import Any

from app.ai.base import LLMProviderError, LLMRequest, LLMResponse
from app.ai.tasks import TASK_CLAIM_ASSESSMENT, TASK_CLAIM_EXTRACTION
from app.services.citations import strip_citations

NO_LIVE_ASSESSMENT = (
    "No live AI assessment was run: the deterministic provider only reproduces the seeded "
    "demo's fixture assessments. Configure LLM_PROVIDER=groq for real assessments."
)


def _normalize(text: str) -> str:
    return " ".join(strip_citations(text).lower().split())


def _looks_factual(sentence: str) -> bool:
    stripped = strip_citations(sentence)
    return not stripped.endswith("?") and len(stripped.split()) >= 4


def _demo_fixture(original_sentence: str) -> dict[str, Any] | None:
    from app.seed.demo import DEMO_CLAIMS  # local import: seed depends on schemas

    wanted = _normalize(original_sentence)
    return next((c for c in DEMO_CLAIMS if _normalize(c["original_sentence"]) == wanted), None)


class DeterministicLLMProvider:
    name = "deterministic"
    model: str | None = None

    async def aclose(self) -> None:
        return None

    async def complete_json(self, request: LLMRequest) -> LLMResponse:
        if request.task == TASK_CLAIM_EXTRACTION:
            output = self._extract(request.payload)
        elif request.task == TASK_CLAIM_ASSESSMENT:
            output = self._assess(request.payload)
        else:
            raise LLMProviderError(
                f"Deterministic provider does not support task {request.task!r}."
            )
        return LLMResponse(content=json.dumps(output), provider=self.name, model=None)

    def _extract(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "claims": [
                {"sentence_id": s["id"], "claim_text": strip_citations(s["text"])}
                for s in payload["sentences"]
                if _looks_factual(s["text"])
            ]
        }

    def _assess(self, payload: dict[str, Any]) -> dict[str, Any]:
        labels = [e["id"] for e in payload["evidence"]]
        fixture = _demo_fixture(payload["original_sentence"])
        if fixture is None:
            return {
                "verdict": "UNVERIFIABLE",
                "confidence_level": "LOW",
                "issues": [{"type": "OTHER", "description": NO_LIVE_ASSESSMENT}],
                "explanation": NO_LIVE_ASSESSMENT,
                "suggested_revision": None,
                "evidence_used": [],
            }
        expected = {passage for passage, _ in fixture["evidence"]}
        used = [e["id"] for e in payload["evidence"] if e["text"] in expected] or labels
        assessment = fixture["assessment"]
        return {
            "verdict": assessment["verdict"],
            "confidence_level": assessment["confidence_level"],
            "issues": assessment["issues"],
            "explanation": assessment["explanation"],
            "suggested_revision": assessment["suggested_revision"],
            "evidence_used": used,
        }

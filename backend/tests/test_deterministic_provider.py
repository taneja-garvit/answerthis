import json

import pytest

from app.ai.base import LLMProviderError, LLMRequest
from app.ai.providers.deterministic import NO_LIVE_ASSESSMENT, DeterministicLLMProvider
from app.ai.schemas import AssessmentOutput, ExtractionOutput
from app.ai.tasks import TASK_CLAIM_ASSESSMENT, TASK_CLAIM_EXTRACTION
from app.seed.demo import POOLED_RESULTS, SENTENCE_2


def _req(task: str, payload: dict) -> LLMRequest:
    return LLMRequest(task=task, prompt_version="v", messages=[], payload=payload)


async def test_extraction_is_one_claim_per_factual_sentence():
    provider = DeterministicLLMProvider()
    payload = {
        "sentences": [
            {"id": "S1", "text": "Drug A lowered blood pressure in adults [1]."},
            {"id": "S2", "text": "Why does this matter?"},
            {"id": "S3", "text": "See below."},
        ]
    }
    response = await provider.complete_json(_req(TASK_CLAIM_EXTRACTION, payload))
    output = ExtractionOutput.model_validate_json(response.content)
    assert [(c.sentence_id, c.claim_text) for c in output.claims] == [
        ("S1", "Drug A lowered blood pressure in adults.")
    ]
    assert response.provider == "deterministic" and response.model is None


async def test_demo_claim_gets_fixture_assessment():
    provider = DeterministicLLMProvider()
    payload = {
        "original_sentence": SENTENCE_2,
        "evidence": [{"id": "E1", "text": "Unrelated."}, {"id": "E2", "text": POOLED_RESULTS}],
    }
    response = await provider.complete_json(_req(TASK_CLAIM_ASSESSMENT, payload))
    output = AssessmentOutput.model_validate_json(response.content)
    assert output.verdict == "PARTIALLY_SUPPORTED"
    assert [i.type for i in output.issues] == ["FIGURE_MISMATCH"]
    assert output.evidence_used == ["E2"]


async def test_other_claims_are_unverifiable_and_say_why():
    provider = DeterministicLLMProvider()
    payload = {
        "original_sentence": "Coffee cures colds [3].",
        "evidence": [{"id": "E1", "text": "x"}],
    }
    output = json.loads(
        (await provider.complete_json(_req(TASK_CLAIM_ASSESSMENT, payload))).content
    )
    assert output["verdict"] == "UNVERIFIABLE"
    assert output["explanation"] == NO_LIVE_ASSESSMENT


async def test_unknown_task_rejected():
    with pytest.raises(LLMProviderError):
        await DeterministicLLMProvider().complete_json(_req("summarize", {}))

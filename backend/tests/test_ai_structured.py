import json

import pytest

from app.ai.base import LLMInvalidOutputError, LLMMessage, LLMRateLimitError, LLMRequest
from app.ai.schemas import AssessmentOutput, ExtractionOutput
from app.ai.structured import StructuredOutputError, generate_structured
from tests.fakes import ScriptedLLM

VALID = {
    "verdict": "SUPPORTED",
    "confidence_level": "HIGH",
    "issues": [],
    "explanation": "Matches.",
    "suggested_revision": None,
    "evidence_used": ["E1"],
}


def _request() -> LLMRequest:
    return LLMRequest(
        task="claim_assessment",
        prompt_version="v-test",
        messages=[LLMMessage("system", "s"), LLMMessage("user", "u")],
    )


def _sequence(*outputs):
    items = list(outputs)
    return ScriptedLLM(lambda _req: items.pop(0))


async def test_valid_output_on_first_call():
    llm = _sequence(VALID)
    result = await generate_structured(llm, _request(), AssessmentOutput, max_retries=2)
    assert result.value.verdict == "SUPPORTED"
    assert result.calls == 1
    assert result.response.model == "scripted-1"


async def test_malformed_json_is_retried_with_feedback():
    llm = _sequence("{not json", VALID)
    result = await generate_structured(llm, _request(), AssessmentOutput, max_retries=2)
    assert result.calls == 2
    repair = llm.requests[1].messages
    assert repair[-2].role == "assistant" and repair[-2].content == "{not json"
    assert "invalid JSON" in repair[-1].content


async def test_schema_violation_is_retried_then_fails_safely():
    bad = {**VALID, "verdict": "TRUE"}
    llm = _sequence(bad, bad, bad, VALID)
    with pytest.raises(StructuredOutputError, match="after 3 attempt"):
        await generate_structured(llm, _request(), AssessmentOutput, max_retries=2)
    assert len(llm.requests) == 3  # bounded: never more than max_retries + 1


async def test_zero_retries_means_one_call():
    llm = _sequence("nope", VALID)
    with pytest.raises(StructuredOutputError):
        await generate_structured(llm, _request(), AssessmentOutput, max_retries=0)
    assert len(llm.requests) == 1


async def test_feedback_lists_field_errors_without_echoing_input():
    secretish = {**VALID, "issues": [{"type": "NOT_A_TYPE", "description": "PRIVATE DRAFT TEXT"}]}
    llm = _sequence(secretish, VALID)
    await generate_structured(llm, _request(), AssessmentOutput, max_retries=1)
    feedback = llm.requests[1].messages[-1].content
    assert "issues.0.type" in feedback
    assert "PRIVATE DRAFT TEXT" not in feedback


async def test_provider_reported_invalid_json_is_retried():
    responses = [LLMInvalidOutputError("bad"), VALID]
    llm = ScriptedLLM(lambda _r: responses.pop(0))
    result = await generate_structured(llm, _request(), AssessmentOutput, max_retries=1)
    assert result.calls == 2


async def test_code_fences_are_tolerated():
    llm = _sequence("```json\n" + json.dumps(VALID) + "\n```")
    result = await generate_structured(llm, _request(), AssessmentOutput, max_retries=0)
    assert result.value.confidence_level == "HIGH"


async def test_transport_errors_propagate_without_validation_retry():
    llm = ScriptedLLM(lambda _r: LLMRateLimitError("slow down"))
    with pytest.raises(LLMRateLimitError):
        await generate_structured(llm, _request(), AssessmentOutput, max_retries=2)
    assert len(llm.requests) == 1


def test_enum_values_are_normalized_but_unknown_values_rejected():
    output = AssessmentOutput.model_validate(
        {
            **VALID,
            "verdict": "partially supported",
            "confidence_level": "medium",
            "issues": [{"type": "figure mismatch", "description": "x"}],
        }
    )
    assert output.verdict == "PARTIALLY_SUPPORTED"
    assert output.issues[0].type == "FIGURE_MISMATCH"
    with pytest.raises(ValueError):
        AssessmentOutput.model_validate({**VALID, "issues": [{"type": "TYPO", "description": "x"}]})


def test_extraction_schema_validates_sentence_ids():
    ExtractionOutput.model_validate({"claims": [{"sentence_id": "S3", "claim_text": "A claim."}]})
    with pytest.raises(ValueError):
        ExtractionOutput.model_validate(
            {"claims": [{"sentence_id": "3", "claim_text": "A claim."}]}
        )
    with pytest.raises(ValueError):
        ExtractionOutput.model_validate({"claims": [{"sentence_id": "S1", "claim_text": ""}]})

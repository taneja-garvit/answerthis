import uuid

import pytest

from app.ai.structured import StructuredOutputError
from app.domain.enums import IssueType, Verdict
from app.services.claim_assessment import (
    RULES_PROVIDER,
    EvidenceInput,
    SourceInput,
    assess_claim,
    rule_unverifiable,
)
from tests.fakes import ScriptedLLM

E1, E2 = uuid.uuid4(), uuid.uuid4()
EVIDENCE = [
    EvidenceInput(
        "E1", E1, "[1]", "Abstract — Results", "ABSTRACT", "Mortality OR 0.81 (95% CI 0.69–0.95)."
    ),
    EvidenceInput("E2", E2, "[1]", "Abstract — Aims", "ABSTRACT", "We studied RPM."),
]
SOURCES = [SourceInput("[1]", "10.1/x", "A paper", "J", 2025, "abstract only")]


async def _assess(output: dict, **kwargs):
    llm = ScriptedLLM(lambda _r: output)
    result = await assess_claim(
        llm,
        claim_text="RPM lowered the odds of death by 22%.",
        original_sentence="It lowered ... [1].",
        sources=SOURCES,
        evidence=EVIDENCE,
        max_retries=kwargs.pop("max_retries", 0),
        **kwargs,
    )
    return llm, result


async def test_valid_assessment_is_mapped_with_metadata():
    llm, result = await _assess(
        {
            "verdict": "PARTIALLY_SUPPORTED",
            "confidence_level": "HIGH",
            "issues": [
                {
                    "type": "FIGURE_MISMATCH",
                    "description": "22% vs OR 0.81",
                    "claim_value": "22%",
                    "evidence_value": "OR 0.81",
                }
            ],
            "explanation": "Direction matches; magnitude does not.",
            "suggested_revision": "…about 19% lower odds…",
            "evidence_used": ["E1", "E9"],
        }
    )
    assert result.verdict == Verdict.PARTIALLY_SUPPORTED
    assert result.evidence_ids == [E1]  # unknown label E9 dropped
    assert result.issues[0].evidence_value == "OR 0.81"
    assert (result.provider, result.model, result.prompt_version) == (
        "scripted",
        "scripted-1",
        "claim_assessment.v1",
    )
    assert result.generation_metadata["usage"] == {"total_tokens": 10}
    payload = llm.requests[0].payload
    assert [e["id"] for e in payload["evidence"]] == ["E1", "E2"]
    assert "Use ONLY the evidence" in llm.requests[0].messages[0].content


async def test_unverifiable_gets_an_evidence_issue():
    _, result = await _assess(
        {
            "verdict": "UNVERIFIABLE",
            "confidence_level": "LOW",
            "issues": [],
            "explanation": "Not addressed.",
            "evidence_used": [],
        }
    )
    assert [i.type for i in result.issues] == [IssueType.INSUFFICIENT_EVIDENCE]
    assert result.evidence_ids == []


async def test_inconsistencies_are_recorded_not_hidden():
    _, result = await _assess(
        {
            "verdict": "SUPPORTED",
            "confidence_level": "MEDIUM",
            "issues": [{"type": "FIGURE_MISMATCH", "description": "x"}],
            "explanation": "ok",
            "evidence_used": [],
        }
    )
    assert set(result.generation_metadata["consistency_warnings"]) == {
        "supported_with_major_issue",
        "evidence_used_missing",
    }
    assert result.evidence_ids == [E1, E2]


async def test_invalid_issue_type_fails_after_retries():
    with pytest.raises(StructuredOutputError):
        await _assess(
            {
                "verdict": "SUPPORTED",
                "confidence_level": "HIGH",
                "issues": [{"type": "MADE_UP", "description": "x"}],
                "explanation": "e",
            },
            max_retries=1,
        )


def test_rule_based_outcome_has_no_model_confidence():
    result = rule_unverifiable(
        IssueType.EVIDENCE_UNAVAILABLE, "No citation is attached to this claim."
    )
    assert result.verdict == Verdict.UNVERIFIABLE
    assert result.confidence_level is None
    assert result.provider == RULES_PROVIDER and result.model is None
    assert result.generation_metadata["live_model"] is False

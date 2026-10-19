"""Claim + source metadata + evidence → AI assessment (a suggestion for review).

Rule-based outcomes (no LLM call) cover the cases where there is nothing for a
model to judge: no citation, unresolvable DOI, no accessible text, or no
relevant passage. Those are UNVERIFIABLE by construction."""

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.ai.base import LLMProvider, LLMRequest
from app.ai.prompts import claim_assessment as prompt
from app.ai.schemas import AssessmentOutput
from app.ai.structured import generate_structured
from app.ai.tasks import TASK_CLAIM_ASSESSMENT
from app.domain.enums import ConfidenceLevel, IssueType, Verdict
from app.schemas.claim import Issue

RULES_PROVIDER = "pipeline_rules"
RULES_VERSION = "pipeline_rules.v1"
_MAJOR = {
    IssueType.FIGURE_MISMATCH,
    IssueType.POPULATION_MISMATCH,
    IssueType.OUTCOME_MISMATCH,
    IssueType.SOURCE_MISMATCH,
}


@dataclass(frozen=True)
class EvidenceInput:
    label: str  # "E1"
    evidence_id: uuid.UUID
    source_label: str  # "[1]"
    location: str | None
    access_level: str
    passage: str


@dataclass(frozen=True)
class SourceInput:
    label: str
    doi: str | None
    title: str | None
    journal: str | None
    year: int | None
    access: str


@dataclass
class AssessmentResult:
    verdict: Verdict
    confidence_level: ConfidenceLevel | None
    issues: list[Issue]
    explanation: str
    suggested_revision: str | None
    evidence_ids: list[uuid.UUID]
    provider: str
    model: str | None
    prompt_version: str
    generation_metadata: dict[str, Any] = field(default_factory=dict)
    llm_calls: int = 0


def rule_unverifiable(
    issue: IssueType, description: str, *, extra: list[Issue] | None = None
) -> AssessmentResult:
    return AssessmentResult(
        verdict=Verdict.UNVERIFIABLE,
        confidence_level=None,  # no model judgement was made
        issues=[Issue(type=issue, description=description), *(extra or [])],
        explanation=(
            f"{description} No AI assessment was run because there is no accessible evidence "
            "to compare the claim with."
        ),
        suggested_revision=None,
        evidence_ids=[],
        provider=RULES_PROVIDER,
        model=None,
        prompt_version=RULES_VERSION,
        generation_metadata={"origin": "pipeline_rule", "live_model": False},
    )


async def assess_claim(
    provider: LLMProvider,
    *,
    claim_text: str,
    original_sentence: str,
    sources: list[SourceInput],
    evidence: list[EvidenceInput],
    max_retries: int,
    extra_issues: list[Issue] | None = None,
) -> AssessmentResult:
    payload = {
        "claim_text": claim_text,
        "original_sentence": original_sentence,
        "sources": [
            {
                "citation": s.label,
                "doi": s.doi,
                "title": s.title,
                "journal": s.journal,
                "year": s.year,
                "text_available": s.access,
            }
            for s in sources
        ],
        "evidence": [
            {
                "id": e.label,
                "citation": e.source_label,
                "location": e.location,
                "access_level": e.access_level,
                "text": e.passage,
            }
            for e in evidence
        ],
    }
    structured = await generate_structured(
        provider,
        LLMRequest(
            task=TASK_CLAIM_ASSESSMENT,
            prompt_version=prompt.PROMPT_VERSION,
            messages=prompt.build_messages(payload),
            payload=payload,
            max_output_tokens=1500,
        ),
        AssessmentOutput,
        max_retries=max_retries,
    )
    output = structured.value
    by_label = {e.label: e.evidence_id for e in evidence}
    used = [by_label[label] for label in output.evidence_used if label in by_label]
    issues: list[Issue] = [Issue.model_validate(i.model_dump()) for i in output.issues]
    warnings: list[str] = []
    if output.verdict == Verdict.UNVERIFIABLE and not any(
        i.type in (IssueType.INSUFFICIENT_EVIDENCE, IssueType.EVIDENCE_UNAVAILABLE) for i in issues
    ):
        issues.append(
            Issue(
                type=IssueType.INSUFFICIENT_EVIDENCE,
                description="The available evidence is not sufficient to assess this claim.",
            )
        )
    if output.verdict == Verdict.SUPPORTED and any(i.type in _MAJOR for i in issues):
        warnings.append("supported_with_major_issue")
    if output.verdict != Verdict.UNVERIFIABLE and not used:
        used = [e.evidence_id for e in evidence]
        warnings.append("evidence_used_missing")
    issues.extend(extra_issues or [])
    response = structured.response
    return AssessmentResult(
        verdict=output.verdict,
        confidence_level=output.confidence_level,
        issues=issues,
        explanation=output.explanation,
        suggested_revision=output.suggested_revision,
        evidence_ids=used,
        provider=response.provider,
        model=response.model,
        prompt_version=prompt.PROMPT_VERSION,
        generation_metadata={
            "origin": "llm" if response.provider != "deterministic" else "deterministic_provider",
            "live_model": response.provider != "deterministic",
            "usage": response.usage,
            "latency_ms": response.latency_ms,
            "llm_calls": structured.calls,
            "consistency_warnings": warnings,
        },
        llm_calls=structured.calls,
    )

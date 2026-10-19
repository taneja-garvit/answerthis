import csv
import io
import re
from datetime import datetime

from app.domain.enums import EvidenceAvailability
from app.schemas.audit import AuditClaim, AuditResponse

CSV_COLUMNS = [
    "claim_number",
    "original_claim",
    "original_sentence",
    "citation",
    "source_title",
    "doi",
    "evidence_availability",
    "evidence_passage",
    "evidence_location",
    "ai_verdict",
    "ai_confidence",
    "ai_provider",
    "issues",
    "ai_explanation",
    "review_status",
    "human_decision",
    "reviewer_note",
    "revised_claim",
    "reviewed_at",
]

# Characters that make spreadsheet applications treat a cell as a formula.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_csv_cell(value: object) -> str:
    """Neutralize spreadsheet formula injection (OWASP CSV injection) by
    prefixing a single quote to any cell that could be read as a formula."""
    if value is None:
        return ""
    text = str(value)
    if text.startswith(_FORMULA_PREFIXES) or text.lstrip().startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


def export_filename(title: str, extension: str, now: datetime) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60].strip("-") or "project"
    return f"evidence-review-{slug}-{now:%Y%m%d}.{extension}"


def _confidence(assessment) -> str:
    if assessment is None:
        return ""
    if assessment.confidence_level is not None:
        return assessment.confidence_level.value
    return f"{assessment.confidence:.2f}" if assessment.confidence is not None else ""


def _csv_row(claim: AuditClaim) -> dict[str, str]:
    unavailable = claim.evidence_availability.status == EvidenceAvailability.UNAVAILABLE
    if unavailable:
        passage = f"[EVIDENCE UNAVAILABLE] {claim.evidence_availability.message}"
        location = "N/A"
    else:
        passage = "\n\n".join(
            ("[SYNTHETIC] " if e.is_synthetic else "") + e.passage for e in claim.evidence
        )
        location = "; ".join(e.location or "unspecified" for e in claim.evidence)

    assessment = claim.assessment
    review = claim.review
    return {
        "claim_number": str(claim.order),
        "original_claim": claim.claim_text,
        "original_sentence": claim.original_sentence,
        "citation": claim.citation_marker or "",
        "source_title": claim.source.title if claim.source else "[NO SOURCE LINKED]",
        "doi": (claim.source.doi or "") if claim.source else "",
        "evidence_availability": claim.evidence_availability.status.value,
        "evidence_passage": passage,
        "evidence_location": location,
        "ai_verdict": assessment.verdict.value if assessment else "NOT_ASSESSED",
        "ai_confidence": _confidence(assessment),
        "ai_provider": assessment.provider if assessment else "",
        "issues": "; ".join(f"{i.type.value}: {i.description}" for i in assessment.issues)
        if assessment
        else "",
        "ai_explanation": assessment.explanation if assessment else "",
        "review_status": claim.review_status.value,
        "human_decision": review.decision.value if review else "NOT_REVIEWED",
        "reviewer_note": (review.reviewer_note or "") if review else "",
        "revised_claim": (review.revised_claim or "") if review else "",
        "reviewed_at": review.reviewed_at.isoformat() if review else "",
    }


def render_csv(audit: AuditResponse) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    for claim in audit.claims:
        writer.writerow({k: sanitize_csv_cell(v) for k, v in _csv_row(claim).items()})
    return buffer.getvalue()


def render_json(audit: AuditResponse) -> str:
    return audit.model_dump_json(indent=2)

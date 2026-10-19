"""Draft text → atomic claims, traceable to their original sentence.

Segmentation, citation parsing and reference lists are deterministic. The LLM
only decides which sentences carry factual claims and splits compound ones.
Its output is then checked against the source sentence: a claim that adds
numbers, causal wording, or drops hedging / statistical terms is replaced by
the original sentence text (citations removed)."""

import logging
import re
from dataclasses import dataclass, field

from app.ai.base import LLMProvider, LLMRequest
from app.ai.prompts import claim_extraction as prompt
from app.ai.schemas import ExtractionOutput
from app.ai.structured import generate_structured
from app.ai.tasks import TASK_CLAIM_EXTRACTION
from app.services.citations import CitationRef, parse_citations, strip_citations
from app.services.evidence_retrieval import extract_numbers
from app.services.segmentation import ParsedDraft, Sentence

logger = logging.getLogger(__name__)

MAX_SENTENCES_PER_CALL = 40
MAX_CLAIMS = 200

_CAUSAL = re.compile(
    r"\b(caus\w*|leads? to|led to|results? in|resulted in|prevent\w*|due to)\b", re.I
)
_HEDGES = re.compile(
    r"\b(may|might|could|associat\w*|suggest\w*|appear\w*|possibl\w*|likely|potential\w*|"
    r"approximately|about|around|nearly|up to|some)\b",
    re.I,
)
_STAT_WORDS = ("odds", "risk", "rate", "hazard", "probability", "likelihood")


@dataclass(frozen=True)
class ExtractedClaimDraft:
    sentence: Sentence
    claim_text: str
    citations: list[CitationRef]
    guard: str | None = None  # why the LLM wording was replaced, if it was


@dataclass
class ExtractionResult:
    claims: list[ExtractedClaimDraft] = field(default_factory=list)
    llm_calls: int = 0
    provider: str | None = None
    model: str | None = None


def guard_claim(sentence_text: str, claim_text: str) -> str | None:
    """Return a reason if the claim wording is not faithful to its sentence."""
    source = strip_citations(sentence_text)
    source_numbers = {n.value for n in extract_numbers(source)}
    if any(n.value not in source_numbers for n in extract_numbers(claim_text)):
        return "added_number"
    if _CAUSAL.search(claim_text) and not _CAUSAL.search(source):
        return "added_causal_wording"
    source_hedges = {h.lower() for h in _HEDGES.findall(source)}
    if source_hedges and not {h.lower() for h in _HEDGES.findall(claim_text)}:
        return "dropped_hedging"
    source_lower, claim_lower = source.lower(), claim_text.lower()
    for word in _STAT_WORDS:
        if word in claim_lower and word not in source_lower:
            return "changed_statistical_term"
    return None


def _dedupe_key(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9.%]+", text.lower()))


async def extract_claims(
    parsed: ParsedDraft, provider: LLMProvider, *, max_retries: int
) -> ExtractionResult:
    result = ExtractionResult(provider=provider.name, model=provider.model)
    sentences = parsed.sentences
    seen: set[str] = set()
    for start in range(0, len(sentences), MAX_SENTENCES_PER_CALL):
        batch = sentences[start : start + MAX_SENTENCES_PER_CALL]
        payload = {"sentences": [{"id": s.id, "text": s.text} for s in batch]}
        structured = await generate_structured(
            provider,
            LLMRequest(
                task=TASK_CLAIM_EXTRACTION,
                prompt_version=prompt.PROMPT_VERSION,
                messages=prompt.build_messages(payload["sentences"]),
                payload=payload,
                max_output_tokens=4096,
            ),
            ExtractionOutput,
            max_retries=max_retries,
        )
        result.llm_calls += structured.calls
        result.model = structured.response.model or result.model
        by_id = {s.id: s for s in batch}
        for item in structured.value.claims:
            sentence = by_id.get(item.sentence_id)
            if sentence is None:
                logger.warning(
                    "extraction referenced unknown sentence",
                    extra={"sentence_id": item.sentence_id},
                )
                continue
            text = " ".join(strip_citations(item.claim_text).split())
            guard = guard_claim(sentence.text, text)
            if guard:
                text = strip_citations(sentence.text)
            key = _dedupe_key(text)
            if not text or key in seen:
                continue
            seen.add(key)
            result.claims.append(
                ExtractedClaimDraft(sentence, text, parse_citations(sentence.text), guard)
            )
    order = {s.id: i for i, s in enumerate(sentences)}
    result.claims.sort(key=lambda c: order[c.sentence.id])  # stable within a sentence
    if len(result.claims) > MAX_CLAIMS:
        result.claims = result.claims[:MAX_CLAIMS]
    guarded = sum(1 for c in result.claims if c.guard)
    logger.info(
        "claims extracted",
        extra={"claims": len(result.claims), "guarded": guarded, "llm_calls": result.llm_calls},
    )
    return result

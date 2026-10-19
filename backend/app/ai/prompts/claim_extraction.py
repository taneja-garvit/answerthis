"""Claim extraction prompt. Bump PROMPT_VERSION whenever the text changes."""

import json

from app.ai.base import LLMMessage

PROMPT_VERSION = "claim_extraction.v1"

SYSTEM = """You extract atomic, independently reviewable factual claims from a research draft.

You receive numbered sentences. Return JSON only, in exactly this shape:
{"claims": [{"sentence_id": "S1", "claim_text": "..."}]}

Rules:
- Only extract factual claims that could be checked against a cited source: findings,
  statistics, effects, associations, comparisons, prevalence, definitions of results.
- Skip headings, opinions, recommendations, transitions, questions, aims or plans, and
  anything that is not a factual assertion. Bibliography entries are not included.
- Split a compound sentence into one claim per independently checkable assertion
  ("X reduced A and B" -> "X reduced A." and "X reduced B."). Do not split further.
- Keep the author's wording. Only change what is needed to make the claim stand alone:
  replace a pronoun such as "It" with the subject it refers to from earlier sentences.
- Never strengthen, weaken or reinterpret a claim. Changing "associated with" into
  "causes" or "reduces", or dropping words like "may", "suggests", "approximately",
  is unacceptable.
- Keep every number, unit, statistic and confidence interval exactly as written. Keep
  the population, intervention, comparator, outcome and any qualifiers.
- Preserve the exact statistical term: risk, odds, rate, hazard and probability are not
  interchangeable.
- Remove citation markers such as [1] or DOIs from claim_text.
- Each claim's sentence_id is the id of the sentence it came from. Keep document order.
  Never extract the same claim twice.
- If there are no factual claims, return {"claims": []}."""


def build_messages(sentences: list[dict[str, str]]) -> list[LLMMessage]:
    return [
        LLMMessage("system", SYSTEM),
        LLMMessage("user", "Sentences (JSON):\n" + json.dumps(sentences, ensure_ascii=False)),
    ]

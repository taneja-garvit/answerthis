"""Evidence retrieval for short documents (abstracts, small user-provided texts).

Strategy `bm25_numeric_v1`: split each section into sentences, rank them with
BM25 against the claim (abbreviations defined in the document, e.g. "heart
failure (HF)", are folded into their long form; a few generic synonyms such as
death/mortality are added), apply a small section prior (Results > Conclusion >
Aims/Background), then boost passages whose numbers match the claim's
numbers (exactly, or as the ratio/percentage counterpart, e.g. "22%" ↔ "OR 0.78")
and that carry statistical notation when the claim is quantitative.

The score measures relevance of a passage to the claim text. It is NOT a
measure of whether the passage supports the claim, nor of scientific truth."""

import math
import re
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Protocol

from app.domain.enums import AccessLevel
from app.services.segmentation import split_sentences

RETRIEVAL_METHOD = "bm25_numeric_v1"

_STOPWORDS = set(
    """a an the and or of in on for to with by from at as is are was were be been being
    this that these those it its their there which who whom than then also into over under
    between among about after before during per vs versus compared not no nor but if so such
    we our they them he she his her has have had do does did can could may might will would
    should shall more most less least very""".split()
)
# Small, generic equivalences; abbreviations are learned from each document.
_SYNONYMS = {
    "death": {"mortality", "died"},
    "mortality": {"death", "died"},
    "died": {"death", "mortality"},
    "hospitalisation": {"hospitalization"},
    "hospitalization": {"hospitalisation"},
    "hospitalized": {"hospitalization"},
    "admission": {"hospitalization"},
}
_STAT_TERMS = re.compile(
    r"\b(OR|RR|HR|CI|ARR|NNT|odds ratio|risk ratio|hazard ratio|relative risk"
    r"|confidence interval)\b|%|\bp\s*[<=>≤]",
)
_TOKEN = re.compile(r"[a-z]+|\d+(?:\.\d+)?")
_NUMBER = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(%)?")
_ABBREVIATION = re.compile(r"((?:[A-Za-z][\w-]*\s+){1,6})[(\[]([A-Z]{2,6})[)\]]")


@dataclass(frozen=True)
class SourceDocument:
    source_id: uuid.UUID
    access_level: AccessLevel
    sections: list[tuple[str, str]]  # (location label, text)


@dataclass(frozen=True)
class EvidenceCandidate:
    source_id: uuid.UUID
    passage: str
    location: str
    access_level: AccessLevel
    retrieval_score: float
    retrieval_method: str
    rank: int


class EvidenceRetriever(Protocol):
    method: str

    def retrieve(
        self, claim_text: str, documents: list[SourceDocument], *, top_k: int = 4
    ) -> list[EvidenceCandidate]: ...


def _stem(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    return [_stem(t) for t in _TOKEN.findall(text.lower().replace("-", " ")) if t not in _STOPWORDS]


@dataclass(frozen=True)
class NumberMention:
    value: float
    percent: bool


def extract_numbers(text: str) -> list[NumberMention]:
    return [NumberMention(float(m.group(1)), bool(m.group(2))) for m in _NUMBER.finditer(text)]


def _number_boost(
    claim_numbers: list[NumberMention], passage_numbers: list[NumberMention]
) -> float:
    boost = 0.0
    for c in claim_numbers:
        best = 0.0
        for p in passage_numbers:
            if c.value == p.value:
                best = max(best, 2.0)
            elif (
                c.percent
                and not p.percent
                and p.value < 2
                and abs((1 - c.value / 100) - p.value) <= 0.03
            ):
                best = max(best, 1.0)  # "22% lower" ↔ ratio 0.78 (or nearby, e.g. 0.81)
            elif (
                p.percent
                and not c.percent
                and c.value < 2
                and abs((1 - c.value) * 100 - p.value) <= 3
            ):
                best = max(best, 1.0)  # ratio in claim ↔ percentage in passage
            elif c.value and abs(c.value - p.value) / abs(c.value) <= 0.1:
                best = max(best, 0.5)
        boost += best
    return min(boost, 4.0)


def learn_abbreviations(text: str) -> dict[str, list[str]]:
    """'heart failure (HF)' → {'hf': ['heart', 'failure']} when the initials match."""
    found: dict[str, list[str]] = {}
    for words, abbr in _ABBREVIATION.findall(text):
        parts = [w for w in re.split(r"[\s-]+", words.strip()) if w]
        candidate = parts[-len(abbr) :]
        if len(candidate) == len(abbr) and all(
            w[0].lower() == a.lower() for w, a in zip(candidate, abbr, strict=True)
        ):
            found[abbr.lower()] = [_stem(w.lower()) for w in candidate]
    return found


def fold_abbreviations(tokens: list[str], abbreviations: dict[str, list[str]]) -> list[str]:
    """Replace an abbreviation token by its long form, so "RPM" and "remote
    patient monitoring" count as the same terms (in queries and passages alike)."""
    folded: list[str] = []
    for token in tokens:
        folded.extend(abbreviations.get(token, [token]))
    return folded


def expand_query(tokens: list[str]) -> list[str]:
    expanded = list(tokens)
    for token in tokens:
        expanded.extend(sorted(_SYNONYMS.get(token, ())))
    return expanded


def section_prior(location: str) -> float:
    """Abstracts put findings in Results/Conclusion; Aims/Background describe the
    question, not the answer. A small nudge, not a filter."""
    label = location.lower()
    if "result" in label or "finding" in label:
        return 1.0
    if "conclusion" in label or "interpretation" in label:
        return 0.5
    if any(word in label for word in ("aim", "background", "introduction", "objective", "purpose")):
        return -0.5
    return 0.0


@dataclass
class _Chunk:
    source_id: uuid.UUID
    access_level: AccessLevel
    location: str
    text: str
    tokens: list[str] = field(default_factory=list)


class LexicalEvidenceRetriever:
    method = RETRIEVAL_METHOD

    def __init__(self, k1: float = 1.5, b: float = 0.75, min_chars: int = 20) -> None:
        self.k1, self.b, self.min_chars = k1, b, min_chars

    def _chunks(
        self, documents: list[SourceDocument], abbreviations: dict[str, list[str]]
    ) -> list[_Chunk]:
        chunks = []
        for doc in documents:
            for location, text in doc.sections:
                for sentence, _, _ in split_sentences(text):
                    if len(sentence) >= self.min_chars:
                        tokens = fold_abbreviations(tokenize(sentence), abbreviations)
                        chunks.append(
                            _Chunk(doc.source_id, doc.access_level, location, sentence, tokens)
                        )
        return chunks

    def retrieve(
        self, claim_text: str, documents: list[SourceDocument], *, top_k: int = 4
    ) -> list[EvidenceCandidate]:
        abbreviations: dict[str, list[str]] = {}
        for doc in documents:
            for _, text in doc.sections:
                abbreviations.update(learn_abbreviations(text))
        chunks = self._chunks(documents, abbreviations)
        if not chunks:
            return []
        query = Counter(expand_query(fold_abbreviations(tokenize(claim_text), abbreviations)))
        claim_numbers = extract_numbers(claim_text)

        n = len(chunks)
        avg_len = sum(len(c.tokens) for c in chunks) / n or 1.0
        doc_freq = Counter(t for c in chunks for t in set(c.tokens))

        scored: list[tuple[float, int, _Chunk]] = []
        for index, chunk in enumerate(chunks):
            tf = Counter(chunk.tokens)
            bm25 = 0.0
            for term in query:
                if term not in tf:
                    continue
                idf = math.log(1 + (n - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5))
                freq = tf[term]
                norm = freq + self.k1 * (1 - self.b + self.b * len(chunk.tokens) / avg_len)
                bm25 += idf * freq * (self.k1 + 1) / norm
            numbers = (
                _number_boost(claim_numbers, extract_numbers(chunk.text)) if claim_numbers else 0.0
            )
            if bm25 <= 0 and numbers < 2.0:
                continue  # no shared content term and no exact number: not relevant
            stats = 0.5 if claim_numbers and _STAT_TERMS.search(chunk.text) else 0.0
            scored.append((bm25 + numbers + stats + section_prior(chunk.location), index, chunk))

        scored.sort(key=lambda item: (-item[0], item[1]))
        return [
            EvidenceCandidate(
                source_id=chunk.source_id,
                passage=chunk.text,
                location=chunk.location,
                access_level=chunk.access_level,
                retrieval_score=round(score, 3),
                retrieval_method=self.method,
                rank=rank,
            )
            for rank, (score, _, chunk) in enumerate(scored[:top_k])
        ]

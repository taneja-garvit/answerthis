"""Deterministic citation parsing: numeric markers and DOIs.

Supported: [1]  [2]  [1, 2]  [1-3] / [1–3]  doi:10.x/…  10.x/…  https://doi.org/10.x/…
Anything else is left alone; the LLM is never asked to find citations."""

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import unquote

_NUM = r"\d{1,4}(?:\s*[-–—]\s*\d{1,4})?"
BRACKET_MARKER = re.compile(rf"\[\s*({_NUM}(?:\s*,\s*{_NUM})*)\s*\]")
_DOI_BODY = r"10\.\d{4,9}/[^\s\"'<>\]]+"
DOI_PATTERN = re.compile(rf"(?:https?://(?:dx\.)?doi\.org/|\bdoi:\s*)?({_DOI_BODY})", re.IGNORECASE)
_DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
_VALID_DOI = re.compile(r"^10\.\d{4,9}/\S+$")
MAX_RANGE = 50


@dataclass(frozen=True)
class CitationRef:
    kind: Literal["number", "doi"]
    value: str  # reference number ("3") or normalized DOI
    label: str  # as written, e.g. "[1-3]" or the DOI


def normalize_doi(raw: str) -> str | None:
    """Lowercase, strip resolver/`doi:` prefixes, URL-decoding and trailing
    punctuation. Returns None if the result is not DOI-shaped."""
    doi = unquote(raw.strip())
    doi = _DOI_PREFIX.sub("", doi).strip()
    # Trailing sentence punctuation is not part of a DOI; a closing bracket is
    # only kept when it balances an opening one (e.g. 10.1016/S0140-6736(20)30183-5).
    while doi and doi[-1] in ".,;:)]}":
        if doi[-1] == ")" and doi.count("(") >= doi.count(")"):
            break
        doi = doi[:-1]
    doi = doi.lower()
    return doi if _VALID_DOI.match(doi) else None


def _expand(group: str) -> list[str]:
    numbers: list[str] = []
    for part in group.split(","):
        bounds = re.split(r"\s*[-–—]\s*", part.strip())
        if len(bounds) == 2:
            start, end = int(bounds[0]), int(bounds[1])
            if start <= end and end - start < MAX_RANGE:
                numbers.extend(str(n) for n in range(start, end + 1))
                continue
        numbers.append(str(int(bounds[0])))
    return numbers


def parse_citations(text: str) -> list[CitationRef]:
    """Citation references in order of appearance, without duplicates."""
    found: list[tuple[int, CitationRef]] = []
    for match in BRACKET_MARKER.finditer(text):
        for number in _expand(match.group(1)):
            found.append((match.start(), CitationRef("number", number, match.group(0))))
    for match in DOI_PATTERN.finditer(text):
        doi = normalize_doi(match.group(1))
        if doi:
            found.append((match.start(), CitationRef("doi", doi, doi)))
    seen: set[tuple[str, str]] = set()
    refs: list[CitationRef] = []
    for _, ref in sorted(found, key=lambda item: item[0]):
        if (ref.kind, ref.value) not in seen:
            seen.add((ref.kind, ref.value))
            refs.append(ref)
    return refs


def marker_label(refs: list[CitationRef]) -> str | None:
    """Compact display label for a claim's citations, e.g. "[1] [3-4]" or "DOI"."""
    labels: list[str] = []
    for ref in refs:
        label = ref.label if ref.kind == "number" else "DOI"
        if label not in labels:
            labels.append(label)
    return " ".join(labels)[:64] or None


_DOI_GROUP = re.compile(rf"\(\s*(?:https?://(?:dx\.)?doi\.org/|doi:\s*)?{_DOI_BODY}\s*\)", re.I)


def strip_citations(text: str) -> str:
    """Remove citation markers and DOIs from a sentence, tidying whitespace."""
    text = BRACKET_MARKER.sub("", text)
    text = _DOI_GROUP.sub("", text)
    text = DOI_PATTERN.sub("", text)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()

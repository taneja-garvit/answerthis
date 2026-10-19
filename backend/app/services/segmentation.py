"""Deterministic draft segmentation: body sentences (with offsets) and the
reference list. Headings and reference entries never become claims."""

import re
from dataclasses import dataclass, field

from app.services.citations import BRACKET_MARKER, DOI_PATTERN, normalize_doi

_ABBREVIATIONS = {
    "al",
    "e.g",
    "i.e",
    "vs",
    "fig",
    "figs",
    "dr",
    "approx",
    "cf",
    "no",
    "eq",
    "ref",
    "refs",
    "ca",
    "etc",
    "resp",
    "min",
    "max",
    "jan",
    "feb",
    "mar",
    "apr",
    "jun",
    "jul",
    "aug",
    "sep",
    "sept",
    "oct",
    "nov",
    "dec",
    "et",
    "st",
    "mr",
    "mrs",
    "ms",
    "prof",
}
_REFERENCE_HEADING = re.compile(
    r"^\s*(?:#+\s*)?(references|bibliography|works cited|literature cited|sources|citations)"
    r"\s*:?\s*$",
    re.IGNORECASE,
)
_REFERENCE_ENTRY = re.compile(r"^\s*(?:\[(\d{1,4})\]|(\d{1,4})\.)\s+(\S.*)$")
_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_BOUNDARY = re.compile(r"[.!?][\"'”’)\]]*\s+(?=[A-Z0-9\[(“\"])")
_LEADING_MARKER = re.compile(rf"^\s*(?:{BRACKET_MARKER.pattern}\s*)+")


@dataclass(frozen=True)
class Sentence:
    id: str  # "S1", "S2", ... in document order
    text: str
    start: int  # character offsets into the original draft
    end: int


@dataclass(frozen=True)
class ReferenceEntry:
    number: str
    text: str
    doi: str | None


@dataclass
class ParsedDraft:
    sentences: list[Sentence] = field(default_factory=list)
    references: dict[str, ReferenceEntry] = field(default_factory=dict)

    def sentence(self, sentence_id: str) -> Sentence | None:
        return next((s for s in self.sentences if s.id == sentence_id), None)


def _is_heading(line: str) -> bool:
    stripped = line.strip()
    if stripped.startswith("#"):
        return True
    return bool(stripped) and stripped[-1] not in '.!?:;)]"”' and len(stripped.split()) <= 12


def _looks_like_reference(line: str) -> bool:
    match = _REFERENCE_ENTRY.match(line)
    return bool(match and match.group(1) and (DOI_PATTERN.search(line) or _YEAR.search(line)))


def split_sentences(text: str, offset: int = 0) -> list[tuple[str, int, int]]:
    """Split a paragraph into (sentence, start, end). Avoids splitting after
    common abbreviations, and keeps a citation marker that follows the full
    stop ("... 0.81. [2] Next") with the sentence it belongs to."""
    pieces: list[tuple[str, int, int]] = []
    start = 0
    for match in _BOUNDARY.finditer(text):
        end = match.start() + 1
        last_word = re.search(r"([A-Za-z.]+)\.$", text[start:end])
        if last_word and last_word.group(1).lower().rstrip(".") in _ABBREVIATIONS:
            continue
        pieces.append((start, end))
        start = match.end()
    if start < len(text):
        pieces.append((start, len(text)))

    merged: list[tuple[str, int, int]] = []
    for s, e in pieces:
        chunk = text[s:e]
        lead = _LEADING_MARKER.match(chunk)
        if lead and merged:
            _, prev_s, _ = merged[-1]
            marker_end = s + lead.end()
            merged[-1] = (text[prev_s:marker_end].strip(), prev_s, marker_end)
            s = marker_end
            chunk = text[s:e]
        stripped = chunk.strip()
        if stripped:
            lstrip = len(chunk) - len(chunk.lstrip())
            merged.append((stripped, s + lstrip, s + lstrip + len(stripped)))
    return [(t, s + offset, e + offset) for t, s, e in merged]


def parse_draft(text: str) -> ParsedDraft:
    parsed = ParsedDraft()
    in_references = False
    paragraph: list[tuple[str, int]] = []
    counter = 0

    def flush() -> None:
        nonlocal counter
        if not paragraph:
            return
        start = paragraph[0][1]
        end = paragraph[-1][1] + len(paragraph[-1][0])
        for sentence, s, e in split_sentences(text[start:end], offset=start):
            counter += 1
            parsed.sentences.append(Sentence(f"S{counter}", sentence, s, e))
        paragraph.clear()

    position = 0
    for line in text.splitlines(keepends=True):
        line_start, position = position, position + len(line)
        content = line.rstrip("\r\n")
        if _REFERENCE_HEADING.match(content):
            flush()
            in_references = True
            continue
        if in_references or _looks_like_reference(content):
            flush()
            match = _REFERENCE_ENTRY.match(content)
            if match:
                number = match.group(1) or match.group(2)
                doi_match = DOI_PATTERN.search(content)
                parsed.references[number] = ReferenceEntry(
                    number=number,
                    text=match.group(3).strip(),
                    doi=normalize_doi(doi_match.group(1)) if doi_match else None,
                )
            continue
        if not content.strip():
            flush()
            continue
        if _is_heading(content) and not paragraph:
            continue
        paragraph.append((content, line_start))
    flush()
    return parsed

import pytest

from app.services.citations import marker_label, normalize_doi, parse_citations, strip_citations
from app.services.segmentation import parse_draft, split_sentences


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10.1002/ejhf.3568", "10.1002/ejhf.3568"),
        ("10.1002/EJHF.3568", "10.1002/ejhf.3568"),
        ("https://doi.org/10.1002/ejhf.3568", "10.1002/ejhf.3568"),
        ("http://dx.doi.org/10.1002/ejhf.3568", "10.1002/ejhf.3568"),
        ("doi:10.1002/ejhf.3568.", "10.1002/ejhf.3568"),
        ("DOI: 10.1002/ejhf.3568;", "10.1002/ejhf.3568"),
        ("https://doi.org/10.1002%2Fejhf.3568", "10.1002/ejhf.3568"),
        ("10.1016/S0140-6736(20)30183-5", "10.1016/s0140-6736(20)30183-5"),
        ("(10.1016/S0140-6736(20)30183-5)", None),  # leading bracket is not part of a DOI
        ("not a doi", None),
        ("10.12/too-short-prefix", None),
    ],
)
def test_normalize_doi(raw, expected):
    assert normalize_doi(raw) == expected


def test_numeric_markers_ranges_and_lists():
    refs = parse_citations("A [1]. B [2, 4]. C [5-7]. D [8–9]. E [1].")
    assert [r.value for r in refs] == ["1", "2", "4", "5", "6", "7", "8", "9"]
    assert {r.label for r in refs if r.value == "6"} == {"[5-7]"}


def test_dois_inline_and_as_urls():
    refs = parse_citations("X (doi:10.1000/abc123). Y https://doi.org/10.1000/XYZ9.")
    assert [(r.kind, r.value) for r in refs] == [("doi", "10.1000/abc123"), ("doi", "10.1000/xyz9")]


def test_oversized_range_is_not_expanded():
    assert [r.value for r in parse_citations("[1-500]")] == ["1"]


def test_non_citation_brackets_ignored():
    assert parse_citations("Values [CI] and [n=40] and [a].") == []


def test_strip_citations_and_label():
    text = "RPM lowered odds (OR 0.78) [1, 2] (doi:10.1000/abc123)."
    assert strip_citations(text) == "RPM lowered odds (OR 0.78)."
    assert marker_label(parse_citations(text)) == "[1, 2] DOI"
    assert marker_label([]) is None


def test_split_sentences_keeps_abbreviations_and_trailing_markers():
    text = "Smith et al. found 3.5% lower odds, e.g. in adults. [2] Next one [1-3]. Done!"
    sentences = [s for s, _, _ in split_sentences(text)]
    assert sentences == [
        "Smith et al. found 3.5% lower odds, e.g. in adults. [2]",
        "Next one [1-3].",
        "Done!",
    ]


def test_offsets_point_into_original_text():
    text = "Title\n\nFirst claim here [1]. Second claim follows.\n\nThird paragraph is here."
    parsed = parse_draft(text)
    for sentence in parsed.sentences:
        assert text[sentence.start : sentence.end] == sentence.text
    assert [s.id for s in parsed.sentences] == ["S1", "S2", "S3"]


def test_headings_and_reference_section_are_not_sentences():
    text = (
        "Background\n"
        "Drug A reduced deaths by 10% [1]. It was well tolerated [2].\n\n"
        "References\n"
        "1. Doe J. A trial of drug A. Lancet. 2020. doi:10.1000/a1\n"
        "[2] Roe K. Tolerability. BMJ 2021. https://doi.org/10.1000/B2\n"
    )
    parsed = parse_draft(text)
    assert [s.text for s in parsed.sentences] == [
        "Drug A reduced deaths by 10% [1].",
        "It was well tolerated [2].",
    ]
    assert parsed.references["1"].doi == "10.1000/a1"
    assert parsed.references["2"].doi == "10.1000/b2"


def test_reference_entries_without_heading_are_detected():
    text = "Claim one is here [1].\n\n[1] Doe J. Title of the paper. 2024. doi:10.1000/x1"
    parsed = parse_draft(text)
    assert len(parsed.sentences) == 1
    assert parsed.references["1"].doi == "10.1000/x1"


def test_reference_without_doi_is_kept_without_doi():
    parsed = parse_draft("Claim one is here [1].\n\nReferences\n[1] Doe J. Some book. 1999.")
    assert parsed.references["1"].doi is None

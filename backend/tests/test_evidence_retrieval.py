import uuid

from app.domain.enums import AccessLevel
from app.seed.demo import COMPONENTS, PAPER, POOLED_RESULTS
from app.services.evidence_retrieval import (
    RETRIEVAL_METHOD,
    LexicalEvidenceRetriever,
    SourceDocument,
    extract_numbers,
    learn_abbreviations,
)

SOURCE = uuid.uuid4()
DOC = SourceDocument(
    SOURCE,
    AccessLevel.ABSTRACT,
    [(f"Abstract — {s['title']}", s["text"]) for s in PAPER["abstract_sections"]],
)


def test_supported_claim_retrieves_the_reported_result_first():
    claim = (
        "Non-invasive remote patient monitoring was associated with lower odds of first "
        "heart-failure hospitalization (OR 0.78)."
    )
    results = LexicalEvidenceRetriever().retrieve(claim, [DOC])
    assert results[0].passage == POOLED_RESULTS
    assert results[0].location == "Abstract — Methods and results"
    assert [r.rank for r in results] == list(range(len(results)))
    assert all(r.retrieval_method == RETRIEVAL_METHOD and r.source_id == SOURCE for r in results)
    assert all(r.access_level == AccessLevel.ABSTRACT for r in results)
    assert results == sorted(results, key=lambda r: -r.retrieval_score)


def test_percentage_claim_matches_ratio_and_synonym():
    # "death" ↔ "mortality", and 22% ↔ ratios near 0.78: the pooled results sentence.
    results = LexicalEvidenceRetriever().retrieve("RPM lowered the odds of death by 22%.", [DOC])
    assert results[0].passage == POOLED_RESULTS


def test_number_aware_boost_beats_lexical_tie():
    doc = SourceDocument(
        SOURCE,
        AccessLevel.USER_PROVIDED,
        [
            (
                "Text",
                (
                    "Exercise lowered systolic blood pressure in older adults overall. "
                    "Exercise lowered systolic blood pressure by 12 mmHg (95% CI 8 to 16)."
                ),
            )
        ],
    )
    results = LexicalEvidenceRetriever().retrieve(
        "Exercise lowered systolic blood pressure by 12 mmHg.", [doc]
    )
    assert results[0].passage.endswith("(95% CI 8 to 16).")


def test_unrelated_claim_returns_nothing():
    assert (
        LexicalEvidenceRetriever().retrieve("Quantum chromodynamics predicts gluon jets.", [DOC])
        == []
    )


def test_empty_documents():
    assert LexicalEvidenceRetriever().retrieve("Anything at all.", []) == []


def test_top_k_and_multiple_sources():
    other = uuid.uuid4()
    doc2 = SourceDocument(other, AccessLevel.ABSTRACT, [("Abstract", COMPONENTS)])
    results = LexicalEvidenceRetriever().retrieve(
        "Self-management modules lowered HF-related hospitalizations.", [DOC, doc2], top_k=2
    )
    assert len(results) == 2
    assert {r.passage for r in results} == {COMPONENTS}
    assert {r.source_id for r in results} == {SOURCE, other}


def test_helpers():
    assert learn_abbreviations("heart failure (HF) and odds ratio [OR]") == {
        "hf": ["heart", "failure"],
        "or": ["odd", "ratio"],
    }
    numbers = extract_numbers("OR 0.81 (95% CI 0.69–0.95), 22% lower")
    assert [(n.value, n.percent) for n in numbers] == [
        (0.81, False),
        (95.0, True),
        (0.69, False),
        (0.95, False),
        (22.0, True),
    ]

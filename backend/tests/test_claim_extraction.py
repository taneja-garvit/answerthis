import pytest

from app.ai.structured import StructuredOutputError
from app.services.claim_extraction import extract_claims, guard_claim
from app.services.segmentation import parse_draft
from tests.fakes import ScriptedLLM

DRAFT = (
    "Results\n"
    "Remote monitoring reduced hospitalization and mortality [1]. "
    "It was associated with fewer emergency visits [2, 3]. We think this is promising.\n\n"
    "References\n[1] A. 2020. doi:10.1000/a\n[2] B. 2021. doi:10.1000/b\n"
)


def _llm(claims):
    return ScriptedLLM(lambda _r: {"claims": claims})


async def test_compound_split_order_and_citations():
    llm = _llm(
        [
            {
                "sentence_id": "S2",
                "claim_text": "Remote monitoring was associated with fewer emergency visits.",
            },
            {"sentence_id": "S1", "claim_text": "Remote monitoring reduced hospitalization."},
            {"sentence_id": "S1", "claim_text": "Remote monitoring reduced mortality."},
        ]
    )
    result = await extract_claims(parse_draft(DRAFT), llm, max_retries=0)
    assert [c.claim_text for c in result.claims] == [
        "Remote monitoring reduced hospitalization.",
        "Remote monitoring reduced mortality.",
        "Remote monitoring was associated with fewer emergency visits.",
    ]
    assert [c.sentence.text for c in result.claims][0] == (
        "Remote monitoring reduced hospitalization and mortality [1]."
    )
    assert [[r.value for r in c.citations] for c in result.claims] == [["1"], ["1"], ["2", "3"]]
    assert result.llm_calls == 1


async def test_only_body_sentences_are_sent_to_the_model():
    llm = _llm([])
    await extract_claims(parse_draft(DRAFT), llm, max_retries=0)
    sent = llm.requests[0].payload["sentences"]
    assert [s["id"] for s in sent] == ["S1", "S2", "S3"]
    assert not any("doi:" in s["text"] or s["text"] == "Results" for s in sent)


async def test_duplicates_unknown_ids_and_markers_are_cleaned():
    llm = _llm(
        [
            {"sentence_id": "S1", "claim_text": "Remote monitoring reduced hospitalization [1]."},
            {"sentence_id": "S1", "claim_text": "remote monitoring reduced hospitalization."},
            {"sentence_id": "S99", "claim_text": "Invented sentence."},
        ]
    )
    result = await extract_claims(parse_draft(DRAFT), llm, max_retries=0)
    assert [c.claim_text for c in result.claims] == ["Remote monitoring reduced hospitalization."]


@pytest.mark.parametrize(
    ("sentence", "claim", "reason"),
    [
        ("RPM lowered odds of death [1].", "RPM lowered odds of death by 22%.", "added_number"),
        (
            "RPM was associated with fewer deaths.",
            "RPM caused fewer deaths.",
            "added_causal_wording",
        ),
        ("RPM may reduce admissions.", "RPM reduces admissions.", "dropped_hedging"),
        (
            "RPM lowered the odds of death.",
            "RPM lowered the risk of death.",
            "changed_statistical_term",
        ),
        (
            "RPM lowered the odds of death by 19% [1].",
            "RPM lowered the odds of death by 19%.",
            None,
        ),
    ],
)
def test_guard_detects_unfaithful_rewrites(sentence, claim, reason):
    assert guard_claim(sentence, claim) == reason


async def test_unfaithful_claim_falls_back_to_original_sentence():
    llm = _llm(
        [{"sentence_id": "S2", "claim_text": "Remote monitoring causes fewer emergency visits."}]
    )
    result = await extract_claims(parse_draft(DRAFT), llm, max_retries=0)
    claim = result.claims[0]
    assert claim.guard == "added_causal_wording"
    assert claim.claim_text == "It was associated with fewer emergency visits."


async def test_malformed_output_retried_then_fails():
    responses = ["not json", {"claims": "nope"}, {"claims": []}]
    llm = ScriptedLLM(lambda _r: responses.pop(0))
    with pytest.raises(StructuredOutputError):
        await extract_claims(parse_draft(DRAFT), llm, max_retries=1)
    assert len(llm.requests) == 2


async def test_long_drafts_are_batched():
    text = " ".join(f"Finding number {i} was observed in the cohort." for i in range(1, 46))
    llm = ScriptedLLM(
        lambda r: {
            "claims": [
                {"sentence_id": s["id"], "claim_text": s["text"]} for s in r.payload["sentences"]
            ]
        }
    )
    result = await extract_claims(parse_draft(text), llm, max_retries=0)
    assert len(llm.requests) == 2
    assert len(result.claims) == 45

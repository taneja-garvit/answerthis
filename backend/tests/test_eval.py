"""Evaluation tooling: dataset integrity and metric arithmetic (no model calls)."""

from app.seed.demo import PAPER
from eval.dataset import load
from eval.metrics import compute


def test_dataset_is_valid_and_honestly_sourced():
    records = load()
    assert 25 <= len(records) <= 35
    categories = {r.category for r in records}
    assert {
        "SUPPORTED",
        "FIGURE_MISMATCH",
        "POPULATION_MISMATCH",
        "OUTCOME_MISMATCH",
        "OVERGENERALIZATION",
        "CAUSAL_OVERSTATEMENT",
        "WORDING_STRENGTH",
        "UNVERIFIABLE",
    } <= categories
    for r in records:
        if r.source.get("synthetic"):
            assert "Synthetic" in r.source["provenance"]
        else:  # real-source evidence must be verbatim from the verified public abstract
            assert r.source["doi"] == PAPER["doi"]
            assert all(e.text in PAPER["abstract"] for e in r.evidence)


def _label(verdict, issues=()):
    return {"expected_verdict": verdict, "expected_issue_types": list(issues)}


def _pred(verdict, issues=()):
    return {"predicted_verdict": verdict, "predicted_issue_types": list(issues)}


def test_metrics_arithmetic():
    pairs = [
        (_label("SUPPORTED"), _pred("SUPPORTED")),  # TN, correct
        (
            _label("UNSUPPORTED", ["OVERGENERALIZATION"]),
            _pred("UNSUPPORTED", ["OVERGENERALIZATION"]),
        ),  # TP
        (
            _label("PARTIALLY_SUPPORTED", ["FIGURE_MISMATCH"]),
            _pred("UNSUPPORTED"),
        ),  # TP, wrong verdict
        (_label("UNSUPPORTED", ["CAUSAL_OVERSTATEMENT"]), _pred("UNVERIFIABLE")),  # FN
        (_label("UNVERIFIABLE"), _pred("UNSUPPORTED")),  # FP
        (_label("SUPPORTED"), {"predicted_verdict": None, "error": "llm_timeout"}),  # error
    ]
    m = compute(pairs)
    assert m["n"] == 6 and m["errors"] == 1
    assert m["verdict_accuracy"] == round(2 / 6, 3)
    assert m["problem_detection"] == {
        "precision": round(2 / 3, 3),
        "recall": round(2 / 3, 3),
        "f1": 0.667,
        "tp": 2,
        "fp": 1,
        "fn": 1,
        "tn": 2,
    }
    assert m["issue_type_recall"] == round(1 / 3, 3)
    assert m["confusion"]["SUPPORTED"] == {"SUPPORTED": 1, "ERROR": 1}


def test_metrics_with_no_positives():
    m = compute([(_label("SUPPORTED"), _pred("SUPPORTED"))])
    assert m["problem_detection"]["precision"] is None
    assert m["problem_detection"]["f1"] is None
    assert m["issue_type_recall"] is None

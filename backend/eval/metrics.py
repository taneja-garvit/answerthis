"""Evaluation metrics. Pure functions over labels and predictions.

Problem detection treats a claim as "problematic" when its verdict is
PARTIALLY_SUPPORTED or UNSUPPORTED (it needs correction). UNVERIFIABLE is not
problematic on either side: a model that answers UNVERIFIABLE for a flawed
claim scores a false negative; one that flags an unverifiable claim as
UNSUPPORTED scores a false positive."""

from collections import Counter
from typing import Any

PROBLEMATIC = {"PARTIALLY_SUPPORTED", "UNSUPPORTED"}
VERDICTS = ["SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "UNVERIFIABLE"]


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 3) if denominator else None


def compute(pairs: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    """`pairs` = [(label, prediction)], label has expected_verdict /
    expected_issue_types, prediction has predicted_verdict / predicted_issue_types
    (or error). Errors count as wrong predictions."""
    n = len(pairs)
    correct = tp = fp = fn = tn = 0
    errors = 0
    issue_expected = issue_found = 0
    confusion: Counter[tuple[str, str]] = Counter()
    for label, prediction in pairs:
        expected = label["expected_verdict"]
        predicted = prediction.get("predicted_verdict") or "ERROR"
        errors += predicted == "ERROR"
        confusion[(expected, predicted)] += 1
        correct += expected == predicted
        exp_problem, pred_problem = expected in PROBLEMATIC, predicted in PROBLEMATIC
        tp += exp_problem and pred_problem
        fp += (not exp_problem) and pred_problem
        fn += exp_problem and not pred_problem
        tn += (not exp_problem) and not pred_problem
        expected_issues = set(label.get("expected_issue_types") or [])
        issue_expected += len(expected_issues)
        issue_found += len(expected_issues & set(prediction.get("predicted_issue_types") or []))

    precision, recall = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
    f1 = (
        round(2 * precision * recall / (precision + recall), 3)
        if precision is not None and recall is not None and (precision + recall)
        else None
    )
    return {
        "n": n,
        "errors": errors,
        "verdict_accuracy": _ratio(correct, n),
        "problem_detection": {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
        },
        "issue_type_recall": _ratio(issue_found, issue_expected),
        "confusion": {
            exp: {
                pred: confusion[(exp, pred)]
                for pred in [*VERDICTS, "ERROR"]
                if confusion[(exp, pred)]
            }
            for exp in VERDICTS
        },
    }

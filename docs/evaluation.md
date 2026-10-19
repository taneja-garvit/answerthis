# Evaluation

This page describes how the claim assessor is evaluated and records the results of real
runs. No metric on this page is estimated or typed by hand: numbers come from
`eval/runs/*.summary.json` files produced by `python -m eval.run_eval`.

## What is measured

The **assessment step** in isolation: given a claim and fixed evidence passages, does the
model return the verdict and issue types a careful human reviewer would? Retrieval is not
part of this evaluation, because the evidence comes from the dataset. End-to-end behaviour
is covered by the pipeline tests and the controlled live test.

## Dataset — `backend/eval/dataset.jsonl`

30 labelled claim/evidence pairs, one JSON object per line:

| Field | Meaning |
|---|---|
| `id`, `category` | e.g. `hf-03`, `FIGURE_MISMATCH` |
| `claim` | the claim as a researcher might write it |
| `evidence` | passages with `text` and `location` |
| `source` | DOI/title, `synthetic` flag and `provenance` |
| `expected_verdict`, `expected_issue_types` | the human label |
| `label_notes` | rationale, including where a second label would be defensible |
| `human_review_status` | `pending` / `approved` / `rejected` |
| `labelled_by`, `reviewed_by` | who drafted, who reviewed |

Composition:

| Category | Records |
|---|---|
| SUPPORTED | 6 |
| FIGURE_MISMATCH | 6 |
| WORDING_STRENGTH | 4 |
| OVERGENERALIZATION | 3 |
| POPULATION_MISMATCH | 3 |
| OUTCOME_MISMATCH | 3 |
| UNVERIFIABLE | 3 |
| CAUSAL_OVERSTATEMENT | 2 |

By expected verdict: 13 UNSUPPORTED, 8 PARTIALLY_SUPPORTED, 6 SUPPORTED, 3 UNVERIFIABLE.
These are the drafted labels; `python -m eval.labels list` shows the current state.

Provenance:
- **13 real-source records (`hf-*`)**: the evidence is exact sentences from the public
  abstract of De Lathauwer et al., *Eur J Heart Fail* 2025, doi:10.1002/ejhf.3568
  (CC BY-NC-ND 4.0). A test checks every passage against the verified abstract.
- **17 synthetic records (`syn-*`)**: the passages were written for this dataset, are
  flagged `"synthetic": true`, and are not quoted from or attributed to any publication.
  They exist to cover reasoning categories (causal overstatement, absolute vs relative
  risk, statistical vs clinical significance, population mismatch) that one abstract cannot.
- `syn-16` has no evidence, so it exercises the rule-based `UNVERIFIABLE` path without an
  LLM call.

### Label status

**All 30 labels are `pending`.** Claude drafted them; no person has reviewed them yet.
Pending labels are **excluded from official metrics**. Several notes flag cases where
another label is defensible (e.g. `hf-05` odds vs probability; `syn-08` UNSUPPORTED vs
UNVERIFIABLE).

Review labels without touching predictions:

```bash
cd backend
.venv/bin/python -m eval.labels list --status pending
.venv/bin/python -m eval.labels show hf-05
.venv/bin/python -m eval.labels approve hf-01 --reviewer "Your Name"
.venv/bin/python -m eval.labels set hf-05 --verdict UNSUPPORTED \
    --issues FIGURE_MISMATCH,WORDING_STRENGTH --reviewer "Your Name" --note "odds vs prob"
.venv/bin/python -m eval.labels reject syn-08 --reviewer "Your Name" --note "ambiguous"
```

## Running

```bash
cd backend
# uses LLM_PROVIDER / LLM_MODEL from .env; 2 s between records for free-tier limits
.venv/bin/python -m eval.run_eval
.venv/bin/python -m eval.run_eval --include-pending      # adds clearly labelled provisional metrics
.venv/bin/python -m eval.run_eval --ids hf-01,hf-03      # subset
```

Each run writes `eval/runs/<UTC timestamp>__<provider>__<model>.jsonl` (one prediction per
record: verdict, issue types, confidence level, explanation, provider, model, prompt
version, token usage, error) and a `.summary.json`. Labels are never written by the runner.
A full run costs 29 LLM calls (30 records, one of them rule-based), plus repair retries if
the model returns invalid output.

## Metrics

Computed by `eval/metrics.py` over **approved** records only:

- **Verdict accuracy**: exact match of the four-way verdict.
- **Problematic-claim detection**: a claim is *problematic* when its verdict is
  `PARTIALLY_SUPPORTED` or `UNSUPPORTED`, i.e. it needs correction. Precision, recall and
  F1 treat problematic as the positive class. `UNVERIFIABLE` is not problematic on either
  side: answering UNVERIFIABLE for a flawed claim is a false negative, and flagging an
  unverifiable claim as UNSUPPORTED is a false positive.
- **Issue-type recall**: the share of expected issue types that appear among the predicted ones.
- **Confusion matrix** of expected versus predicted verdicts; failed calls count as `ERROR`.

`--include-pending` adds a separate `provisional_including_unreviewed_labels` block. Those
numbers are not official and must not be quoted as results.

## Results

**No official results yet.** Official metrics need approved labels, and none are approved.

No live evaluation run has been made. A controlled live smoke test of the full pipeline on
the three heart-failure demo claims is recorded in the README under
[Live validation](../README.md#live-validation). It is not an accuracy benchmark.

# Product

## Problem

A researcher's draft contains factual claims with citations. AI-assisted tools can flag
where a claim may not match its source — a wrong figure, a broader population, a causal
verb where the study shows association. But a flag is not a decision. The researcher has
to look at the evidence, judge it, fix the wording, and leave a record collaborators can
trust.

This prototype explores a structured human review workflow around AI-assisted claim
verification: pull-request review, but for claims.

## Principles

1. **AI assists, human decides.** The UI and API call it an *AI assessment*, never a
   verdict of truth. A claim becomes *reviewed* only when a person records a decision.
2. **Evidence first.** Every assessment is tied to the exact passages it was based on,
   with their access level (abstract, open-access full text, user-provided).
3. **Honest gaps.** When evidence cannot be accessed the system says so
   (`UNAVAILABLE` / `UNVERIFIABLE`) instead of inventing support.
4. **Traceable decisions.** Each decision keeps its note, revised wording, timestamp,
   the assessment the reviewer saw, and the history of earlier decisions.
5. **Retrieval score ≠ support.** Similarity scores rank passages; they are not evidence
   that a claim is true.

## Core flow

1. Create a project and paste a draft (Phase 1–2: done).
2. Analyze: extract atomic claims, resolve citations, retrieve evidence, assess (Phase 3).
3. Review each claim: inspect evidence and the AI assessment, choose a decision, add a
   note and optional revised claim, save, move on (API done; UI Phase 4).
4. Track progress; when complete, export the audit trail as CSV or JSON (done).

## Decisions

| Decision | Meaning | `revised_claim` |
|---|---|---|
| `KEEP` | claim stands as written | must be empty |
| `QUALIFY` | claim stays, wording adjusted (e.g. figure, hedging) | optional |
| `REPLACE` | claim replaced with a different statement | required |
| `REMOVE` | claim dropped from the draft | must be empty |

Rejecting a revised claim on KEEP/REMOVE, rather than silently discarding it, avoids
losing reviewer text.

## AI assessment vocabulary

Verdicts: `SUPPORTED`, `PARTIALLY_SUPPORTED`, `UNSUPPORTED`, `UNVERIFIABLE`.

Issue types: `FIGURE_MISMATCH`, `POPULATION_MISMATCH`, `OUTCOME_MISMATCH`,
`OVERGENERALIZATION`, `CAUSAL_OVERSTATEMENT`, `WORDING_STRENGTH`, `SOURCE_MISMATCH`,
`INSUFFICIENT_EVIDENCE`, `EVIDENCE_UNAVAILABLE`, `OTHER`. Each issue can carry the
conflicting `claim_value` and `evidence_value` (e.g. "22%" vs "OR 0.81 ≈ 19%").

Progress reports human decisions and AI verdicts as **separate** distributions.

## Seeded demo

A three-claim heart-failure draft citing doi:10.1002/ejhf.3568, with evidence quoted
verbatim from the paper's public abstract:

1. Hospitalization claim matching the reported OR 0.78 — fixture `SUPPORTED`.
2. "Lowered the odds of death by 22%" while the source reports OR 0.81 (≈19%) —
   fixture `PARTIALLY_SUPPORTED` with `FIGURE_MISMATCH`.
3. "Works for every heart-failure patient" — fixture `UNSUPPORTED` with
   `OVERGENERALIZATION`.

Fixture assessments are labelled `provider = demo_fixture`, `live_model = false`.

## Out of scope for the MVP

Proving scientific truth; searching the whole literature; bypassing paywalls;
rewriting manuscripts; real-time collaboration; auth, billing, teams, permissions;
vector infrastructure.

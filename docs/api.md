# API reference

Base URL (local): `http://localhost:8000`. Interactive OpenAPI docs at `/docs`.
All bodies are JSON. IDs are UUIDs; a malformed ID returns `422`.

## Endpoints

| Method | Path | Purpose | Success |
|---|---|---|---|
| GET | `/health` | API up and database reachable | 200 / 503 |
| POST | `/api/projects` | create a project | 201 + `Location` |
| GET | `/api/projects/{project_id}` | project with draft summaries | 200 |
| POST | `/api/projects/{project_id}/drafts` | store a draft | 201 + `Location` |
| GET | `/api/drafts/{draft_id}` | one draft | 200 |
| GET | `/api/drafts/{draft_id}/claims` | all claims of a draft, composite | 200 |
| POST | `/api/drafts/{draft_id}/analyze` | run the AI pipeline (synchronous) | 200 |
| GET | `/api/claims/{claim_id}` | one composite claim | 200 |
| POST | `/api/claims/{claim_id}/assess` | re-run retrieval + assessment for one claim | 200 |
| PUT | `/api/claims/{claim_id}/review` | save the human decision | 200 |
| GET | `/api/projects/{project_id}/progress` | review progress + distributions | 200 |
| GET | `/api/projects/{project_id}/audit` | structured audit trail | 200 |
| GET | `/api/projects/{project_id}/export?format=csv\|json` | download audit trail | 200 (attachment) |
| POST | `/api/demo[?reset=true]` | create/load the seeded demo | 201 created / 200 existing |


## Health

```json
200 {"status": "ok", "database": "connected"}
503 {"status": "degraded", "database": "unavailable"}
```

## Projects and drafts

`POST /api/projects` — `{"title": "…" (1–300, trimmed), "description": "…" (optional, ≤2000)}`

```json
{
  "id": "…", "title": "…", "description": null, "status": "ACTIVE", "is_demo": false,
  "drafts": [{"id": "…", "char_count": 520, "claim_count": 3, "created_at": "…Z"}],
  "created_at": "…Z", "updated_at": "…Z"
}
```

`POST /api/projects/{id}/drafts` — `{"original_text": "…"}`. Text is trimmed; empty →
`422 draft_empty`; longer than `MAX_DRAFT_CHARS` → `422 draft_too_large`. Drafts (and
project draft summaries) carry `analysis_status`: `NOT_ANALYZED`, `ANALYZING`,
`ANALYZED` or `FAILED`.

## Analyze a draft

`POST /api/drafts/{draft_id}/analyze` — body optional:

```jsonc
{
  "mode": "resume",                          // or "reextract"
  "citations": {"1": "10.1002/ejhf.3568"},   // optional marker → DOI, overrides the reference list
  "refresh_metadata": false                   // true bypasses the DOI metadata cache
}
```

Runs synchronously: segment the draft and parse citations (deterministic) → extract
claims (LLM) → resolve DOIs (cache → Crossref + OpenAlex) → retrieve evidence from the
public abstract → assess each claim (LLM, or a rule when there is nothing to assess) →
persist. Response:

```json
{
  "draft_id": "…", "project_id": "…", "analysis_status": "ANALYZED",
  "rerun": false,
  "claims_extracted": 3, "claims_processed": 3, "claims_reused": 0,
  "claims_assessed": 3, "claims_unverifiable": 0, "claims_failed": 0,
  "llm_provider": "groq", "llm_model": "<LLM_MODEL>", "llm_calls": 4,
  "claims": [ClaimReviewResponse, …]
}
```

Re-run behaviour:

| Situation | Result |
|---|---|
| Draft has no claims | claims are extracted, then processed |
| `mode: resume` (default), claims exist | claims with status `READY` and an assessment are reused (no LLM calls); `PENDING`/`ERROR` or unassessed claims are processed |
| `mode: reextract`, no reviews | claims are deleted and re-extracted |
| `mode: reextract`, any claim reviewed | `409 reviews_exist` (decisions are never discarded) |
| Draft already being analyzed | `409 analysis_in_progress` (a lock older than 15 min is taken over) |

Failures are isolated per claim. A claim whose citation cannot be resolved, whose DOI
does not exist, or whose source has no accessible text gets a rule-based `UNVERIFIABLE`
assessment (`provider: "pipeline_rules"`, no LLM call). A claim that fails for a
transient reason (metadata providers down, LLM timeout or rate limit) gets
`status: "ERROR"` and a `processing_error`; the next analyze call retries it. After a
rate-limit or authentication error, remaining claims are skipped, not attempted.

If claim extraction itself fails, the request returns the provider error (see Errors)
and the draft's `analysis_status` becomes `FAILED`.

## Reassess one claim

`POST /api/claims/{claim_id}/assess` — body optional: `{"refresh_metadata": false}`.

Re-runs citation resolution, retrieval and assessment for one claim and **appends** a new
assessment; the newest assessment is current, earlier ones stay in the database, and an
existing human review is untouched. Evidence rows that are retrieved again are reused;
passages no longer retrieved are marked `is_current = false` (kept, because earlier
assessments cite them) and are no longer shown. If reassessment fails, the error is
returned, the previous assessment stays current and `processing_error` explains what
happened. Returns the updated `ClaimReviewResponse`.

## Composite claim (`ClaimReviewResponse`)

Everything the review screen needs in one response:

```json
{
  "id": "…", "draft_id": "…", "project_id": "…", "order": 2,
  "claim_text": "Non-invasive remote patient monitoring lowered the odds of death by 22%.",
  "original_sentence": "It lowered the odds of death by 22% [1].",
  "citation_marker": "[1]",
  "status": "READY",
  "processing_error": null,
  "source": {
    "id": "…", "doi": "10.1002/ejhf.3568", "title": "Remote Patient Monitoring in Heart Failure: …",
    "authors": [{"given": "Ignace L.J.", "family": "De Lathauwer", "orcid": "…"}],
    "journal": "European Journal of Heart Failure", "publication_year": 2025,
    "open_access_url": "…", "access_status": "ABSTRACT_ONLY", "citation_marker": "[1]"
  },
  "sources": ["… all linked sources, primary first …"],
  "evidence": [{
    "id": "…", "source_id": "…",
    "passage": "RPM was associated with lower mortality risk (pooled odds ratio [OR] 0.81 …",
    "location": "Abstract — Methods and results", "access_level": "ABSTRACT",
    "retrieval_method": "seed_fixture", "retrieval_score": null, "rank": 0, "is_synthetic": false
  }],
  "evidence_availability": {
    "status": "ABSTRACT",
    "message": "Assessment limited to the public abstract; the full text was not reviewed."
  },
  "assessment": {
    "id": "…", "verdict": "PARTIALLY_SUPPORTED",
    "confidence_level": "HIGH", "confidence": null,
    "issues": [{
      "type": "FIGURE_MISMATCH",
      "description": "The claimed reduction (22%) does not match …",
      "claim_value": "22% lower odds of death",
      "evidence_value": "pooled OR 0.81 (95% CI 0.69–0.95), ≈19% lower odds"
    }],
    "explanation": "…", "suggested_revision": "…", "evidence_ids": ["…"],
    "provider": "demo_fixture", "model": null, "prompt_version": null,
    "generation_metadata": {"origin": "seed_fixture", "live_model": false, "…": "…"},
    "created_at": "…Z"
  },
  "review": null,
  "review_status": "NEEDS_REVIEW"
}
```

- `assessment` is the newest assessment, or `null`.
- `confidence_level` (`LOW`/`MEDIUM`/`HIGH`) is the assessor's confidence in its
  claim-versus-evidence classification, not a probability that the claim is true. It is
  `null` for rule-based outcomes. The numeric `confidence` is reserved for providers with
  calibrated scores and is `null` today.
- `evidence` lists the passages from the latest retrieval. `retrieval_score` is lexical
  relevance to the claim, not a measure of support or truth.
- `provider` is `groq` (live model), `deterministic` (offline provider), `pipeline_rules`
  (no model call) or `demo_fixture` (seeded, hand-authored).
- `evidence_availability.status` is one of `FULL_TEXT`, `ABSTRACT`, `USER_PROVIDED`,
  `UNAVAILABLE`. With `UNAVAILABLE`, `evidence` is empty and `message` says why.
- `review_status` is `REVIEWED` only when a human decision exists.

`GET /api/drafts/{id}/claims` → `{"draft_id": "…", "project_id": "…", "claims": [ClaimReviewResponse…]}`
ordered by `order`.

## Saving a review

`PUT /api/claims/{claim_id}/review`

```json
{"decision": "QUALIFY", "reviewer_note": "Changed 22% to 19%.", "revised_claim": "…"}
```

| decision | revised_claim |
|---|---|
| KEEP | must be absent/blank (else 422) |
| QUALIFY | optional |
| REPLACE | required (else 422) |
| REMOVE | must be absent/blank (else 422) |

Blank strings are stored as `null`. Limits: note ≤ 5000, revised claim ≤ 2000 chars.
Each save updates the single current review (`reviewed_at` set to now) and appends an
immutable `review_event`. Returns the updated `ClaimReviewResponse`.

## Progress

```json
{
  "project_id": "…", "total_claims": 3, "reviewed_claims": 3, "remaining_claims": 0,
  "completion_percentage": 100.0, "is_complete": true,
  "human_decisions": {"KEEP": 1, "QUALIFY": 1, "REPLACE": 0, "REMOVE": 1},
  "ai_verdicts": {"SUPPORTED": 1, "PARTIALLY_SUPPORTED": 1, "UNSUPPORTED": 1,
                  "UNVERIFIABLE": 0, "NOT_ASSESSED": 0}
}
```

With zero claims: all counts 0, `completion_percentage` 0.0, `is_complete` false.
`ai_verdicts` counts only each claim's newest assessment.

## Audit and export

`GET /api/projects/{id}/audit` (and `export?format=json`, as an attachment):

```json
{
  "export_version": "1", "generated_at": "…Z",
  "disclaimer": "AI assessments are suggestions … They do not establish scientific truth. …",
  "project": {"id": "…", "title": "…", "description": "…"},
  "progress": { "…": "as above" },
  "claims": [{ "…ClaimReviewResponse…": "", "review_history": [
    {"id": "…", "decision": "KEEP", "previous_decision": null, "reviewer_note": null,
     "revised_claim": null, "assessment_id": "…", "created_at": "…Z"}
  ]}]
}
```

`export?format=csv` — UTF-8 with BOM, all fields quoted, one row per claim. Columns:

`claim_number, original_claim, original_sentence, citation, source_title, doi,
evidence_availability, evidence_passage, evidence_location, ai_verdict, ai_confidence
(confidence level, or a number for providers that give one),
ai_provider, issues, ai_explanation, review_status, human_decision, reviewer_note,
revised_claim, reviewed_at`

- Unavailable evidence: `evidence_passage` = `[EVIDENCE UNAVAILABLE] <reason>`,
  `evidence_location` = `N/A`. Never blank.
- Unassessed: `ai_verdict` = `NOT_ASSESSED`. Unreviewed: `human_decision` = `NOT_REVIEWED`.
- Multiple passages are separated by a blank line; locations by `; `.
- Formula injection: cells starting with `= + - @`, tab or CR are prefixed with `'`.
- Filename: `evidence-review-<slugified-title>-<yyyymmdd>.<ext>`.

## Errors

Every error uses one envelope, and every response carries `X-Request-ID`:

```json
{"error": {"code": "not_found", "message": "Claim not found", "request_id": "…", "details": […]}}
```

| Status | code | When |
|---|---|---|
| 404 | `not_found` | unknown project/draft/claim or route |
| 405 | `method_not_allowed` | wrong method |
| 422 | `validation_error` | malformed body, ID or query (`details`: `loc`, `msg`, `type`; input never echoed) |
| 422 | `draft_empty`, `draft_too_large` | draft rules |
| 409 | `analysis_in_progress`, `reviews_exist` | see Analyze |
| 503 | `database_unavailable` | database unreachable (no connection details exposed) |
| 503 | `llm_rate_limited` | Groq rate limit persisted after bounded retries (`Retry-After` set when known) |
| 503 | `metadata_providers_unavailable` | Crossref and OpenAlex both unreachable (reassess) |
| 504 | `llm_timeout` | AI provider timed out after retries |
| 502 | `llm_auth_failed`, `llm_provider_error`, `llm_invalid_output` | key rejected; provider rejected the request (e.g. unknown model); output still invalid after repair retries |
| 500 | `internal_error` | unexpected failure |

# Architecture

Status: Phases 1–3 (foundation, review domain, AI pipeline). The frontend (Phase 4)
consumes the API described in [api.md](api.md).

## Layers

```
HTTP ──► RequestIDMiddleware ──► CORS ──► route (api/routes/*)
                                           │  validates input (Pydantic), injects session
                                           ▼
                                        service (services/*)
                                           │  domain rules, owns commit
                                           ▼
                               repository / ORM (repositories/*, models/*)
                                           ▼
                                   PostgreSQL (Neon)
```

- **Routes are thin.** They parse input, call one service function and return a schema.
- **Services own transactions.** One request = one session = one unit of work; the
  service commits. Uncommitted work is rolled back when the session closes.
- **Repositories** exist only where a query is non-trivial (eager-loading the composite
  claim view, review history).
- **Providers** sit behind protocols (`app/ai/base.py` `LLMProvider`,
  `app/papers/base.py` `PaperProvider`) and are called only from services. Concrete
  providers are built once per process (`app/ai/factory.py`, `app/papers/factory.py`)
  and injected through `app.state`; tests inject fakes.

## AI pipeline

```
POST /api/drafts/{id}/analyze ─► PipelineService.analyze_draft          services/pipeline.py
  1. lock the draft (analysis_status = ANALYZING)
  2. segment into sentences + reference list      deterministic    services/segmentation.py
  3. extract claims                               LLM              services/claim_extraction.py
     └ faithfulness guard: added numbers or causal words, dropped hedges, or a changed
       odds/risk/rate term → the claim falls back to the original sentence
  then for each claim, committed one at a time:
  4. parse citation markers / DOIs                deterministic    services/citations.py
  5. resolve DOIs: memo → paper_cache → Crossref ∥ OpenAlex → merge → cache
                                                                   services/citation_resolution.py
  6. upsert the project's Source rows, link claim_sources
  7. retrieve evidence from the public abstract   BM25 + numbers   services/evidence_retrieval.py
  8. assess                                       LLM, or a rule   services/claim_assessment.py
  9. append an Assessment; claim → READY (or ERROR with processing_error)
```

The pipeline is synchronous for the MVP. Each stage is a function with explicit inputs,
so orchestration can move behind a job queue without rewriting the stages. It commits
after each stage and each claim, so earlier claims survive a later failure and no
transaction is held open while waiting on the LLM. Re-run rules are in
[api.md](api.md#analyze-a-draft).

### LLM layer (`app/ai/`)

- `base.py`: the `LLMProvider` protocol (`complete_json(LLMRequest) -> LLMResponse`) and
  typed errors (`LLMAuthError`, `LLMRateLimitError`, `LLMTimeoutError`,
  `LLMProviderError`, `LLMInvalidOutputError`) whose messages are safe to show users.
- `structured.py`: `generate_structured(provider, request, Schema, max_retries)` parses
  JSON (tolerating code fences) and validates it with Pydantic. On failure it re-asks with
  the validation errors (locations and messages only, never input values), at most
  `LLM_MAX_RETRIES` more times, then raises `StructuredOutputError`. It cannot loop forever.
- `schemas.py`: `ExtractionOutput` and `AssessmentOutput`. Enum values are
  case-normalized; unknown verdicts or issue types are rejected, which triggers a repair retry.
- `prompts/`: one module per task with a `PROMPT_VERSION` (`claim_extraction.v1`,
  `claim_assessment.v1`), stored on every assessment.
- `providers/groq.py`: Groq's OpenAI-compatible chat API over httpx, in JSON mode at
  temperature 0. It retries 429 (honouring `Retry-After`), 5xx, timeouts and network errors
  with bounded exponential backoff (at most `LLM_MAX_RETRIES` retries, each wait ≤ 20 s).
  401/403 and other 4xx responses are not retried. Groq's `json_validate_failed` maps to
  `LLMInvalidOutputError`, so the structured layer repairs it. The key only ever goes in
  the Authorization header. Logs record task, model, latency, attempts and token usage,
  never prompts, drafts or keys.
- `providers/deterministic.py`: the offline provider. Extraction is one claim per
  factual-looking sentence. Assessment reproduces the seeded demo's fixtures for demo
  claims and returns `UNVERIFIABLE` ("no live AI assessment was run") for anything else.
  It never pretends to assess.

Free-tier awareness: deterministic work never goes to the LLM; claims with nothing to
assess get rule outcomes without a call; claims that are already assessed are not
re-assessed on re-run; a rate-limit or auth error stops further calls for the rest of the
run; DOI metadata is cached. A three-claim draft costs 4 LLM calls (1 extraction +
3 assessments).

### Paper metadata (`app/papers/`)

- `CrossrefProvider` (`/works/{doi}`): title, authors, journal, publisher, year, licence,
  and the JATS abstract when the publisher deposited one, kept as titled sections.
- `OpenAlexProvider` (`/works/https://doi.org/{doi}`): open-access status and location,
  and the abstract reconstructed from OpenAlex's inverted index.
- Both use `http.get_json`: a `HTTP_TIMEOUT_SECONDS` timeout and bounded retries on
  429/5xx/timeouts honouring `Retry-After`. A 404 means "not found"; any other failure
  raises a typed `PaperProviderError`. `CONTACT_EMAIL`, if set, is sent as `mailto` (the
  "polite pool"); `OPENALEX_API_KEY` is optional.
- `PaperResolver` queries both providers concurrently and merges the results: Crossref
  first for bibliographic fields and structured abstracts, OpenAlex for open-access data
  and to fill gaps. Results are cached in `paper_cache` for `PAPER_CACHE_TTL_DAYS`, "DOI not
  found" for one day, and provider outages never. A per-run memo prevents repeat lookups
  within one analysis.
- If the draft's reference entry does not match the resolved title (word overlap below
  30%), a `SOURCE_MISMATCH` issue is added: the DOI may be wrong.

### Evidence access rules

Evidence comes only from the public abstract (Crossref or OpenAlex). Open-access full
text is linked (`open_access_url`) but not fetched or parsed yet, so sources are
`ABSTRACT_ONLY` or `UNAVAILABLE`. Nothing behind a paywall is accessed, and metadata is
never treated as evidence. When there is nothing to compare against, the claim gets a
rule-based `UNVERIFIABLE` without an LLM call:

| Situation | Issue type |
|---|---|
| no citation in the sentence | `EVIDENCE_UNAVAILABLE` |
| marker with no reference entry or DOI | `EVIDENCE_UNAVAILABLE` |
| DOI unknown to Crossref and OpenAlex | `SOURCE_MISMATCH` |
| source has no public abstract | `EVIDENCE_UNAVAILABLE` |
| no passage shares content with the claim | `INSUFFICIENT_EVIDENCE` |

These are product outcomes, not errors. Only transient failures (a provider outage, an
LLM timeout or rate limit) produce `status: ERROR`, which a re-run retries.

### Evidence retrieval

`LexicalEvidenceRetriever` (`bm25_numeric_v1`) implements the `EvidenceRetriever`
protocol. It splits abstract sections into sentences and ranks them with BM25 (k1 1.5,
b 0.75), plus:

- abbreviations defined in the document ("heart failure (HF)") folded into their long
  form in both query and passages, and a few generic synonyms (death ↔ mortality);
- a small section prior (Results +1, Conclusion +0.5, Aims/Background −0.5);
- number-aware boosts: an exact number match +2; a claim percentage matching the
  corresponding ratio (22% ↔ 0.78, within 0.03) or the reverse +1; a nearby value +0.5;
  statistical notation (OR, RR, HR, CI, %, p-values) +0.5 when the claim is quantitative.

It returns the top 4 passages that share at least one content term (or an exact number)
with the claim. The score measures relevance of a passage to the claim text. It is not
confidence that the claim is supported, and it is not presented that way. No embeddings
or vector store are used.

### Assessment semantics

The assessor sees the claim, the cited sources' metadata (labelled as identification,
not evidence) and the numbered passages. The prompt requires judging from the evidence
only: no outside knowledge, no assumptions about sections it has not seen. It must compare
population, intervention, comparator, outcome, direction, numbers, statistical quantity,
scope, causal wording and certainty wording, and prefer `UNVERIFIABLE` to guessing.

Post-processing does three things:
- maps the passages the model says it used (`evidence_used`) to evidence ids;
- adds `INSUFFICIENT_EVIDENCE` to an `UNVERIFIABLE` verdict that lacks it;
- records inconsistencies (e.g. `SUPPORTED` together with a figure mismatch) in
  `generation_metadata.consistency_warnings`, rather than silently changing the model's answer.

**Confidence.** LLM self-reported probabilities are not calibrated, and a value like 0.86
suggests precision that does not exist. The assessor therefore reports a coarse
`confidence_level` (`LOW` / `MEDIUM` / `HIGH`, with a rubric in the prompt). It describes
confidence in the claim-versus-evidence classification, never in the truth of the science.
Rule-based outcomes have no confidence (`null`). The numeric `confidence` column is
nullable and reserved for a provider that can supply a calibrated score.

## Data model

```
projects ─┬─< drafts ─< claims ─┬─< claim_sources >── sources >── projects
          │                     ├─< evidence ──────── sources
          └─< sources           ├─< assessments           (append-only history)
                                ├── reviews (0..1)  ─< review_events  (append-only)
paper_cache  (global, keyed by DOI)
```

| Table | Purpose | Key constraints / indexes |
|---|---|---|
| `projects` | review workspace | `status` CHECK; `seed_key` UNIQUE (idempotent demo) |
| `drafts` | pasted research text | FK project (CASCADE); index `project_id`; `analysis_status` CHECK (also the analysis lock), `analysis_started_at`, `analyzed_at` |
| `sources` | cited work, per project | FK project (CASCADE); `access_status` CHECK; partial UNIQUE `(project_id, doi) WHERE doi IS NOT NULL` |
| `paper_cache` | provider metadata shared across projects | `doi` UNIQUE (normalized lowercase) |
| `claims` | atomic claim, traceable to its sentence | FK draft (CASCADE); UNIQUE `(draft_id, position)`; `status` CHECK; `processing_error` |
| `claim_sources` | claim ↔ cited sources (many-to-many) | PK `(claim_id, source_id)`; per-source `citation_marker`; `position` 0 = primary |
| `evidence` | passage from a source for a claim | FKs claim + source (CASCADE); `access_level` CHECK; `is_synthetic`; `is_current` (false once superseded by a later retrieval) |
| `assessments` | AI/rule/fixture assessment; newest = current | FK claim (CASCADE); `verdict` and `confidence_level` CHECKs; nullable `confidence` 0..1; index `(claim_id, created_at)`; provider/model/prompt_version/usage recorded |
| `reviews` | current human decision | FK claim UNIQUE (one per claim); `decision` CHECK |
| `review_events` | immutable decision history | FKs claim, review (CASCADE), assessment (SET NULL); index `(claim_id, created_at)` |

Design decisions:

- **Enums are `VARCHAR` + `CHECK`**, mirrored by Python `StrEnum`s. Adding a value is a
  constraint swap, not `ALTER TYPE`.
- **Assessments are history.** Re-assessing appends a row; reproducibility metadata
  (`provider`, `model`, `prompt_version`, `generation_metadata`, `evidence_ids`) stays
  with each one. Issues are a JSONB list validated by `schemas.claim.Issue` before writing.
- **Reviews have a current row plus an event log.** `PUT /review` upserts `reviews` and
  appends to `review_events` in one transaction; the claim row is locked
  (`SELECT … FOR UPDATE`) so concurrent saves serialize. Each event records the
  previous decision and the assessment the reviewer was shown.
- **Multi-source ready.** Claims link to sources through `claim_sources`, and evidence
  links to both claim and source, so multi-citation claims need no migration. The MVP
  treats position 0 as the primary source.
- **Derived, not stored:** review status (`REVIEWED` iff a review exists), evidence
  availability, and progress. Nothing marks a claim reviewed except a human decision.
- **Unavailable evidence is explicit.** `evidence_availability` is computed from evidence
  rows and the source's `access_status` and is shown as `UNAVAILABLE` with a reason
  (no source / source inaccessible / no relevant passage), in the API and in exports.
- Timestamps are `timestamptz`; the API always emits UTC.

## Database connection handling (Neon)

- `DATABASE_URL` is used as given; `postgres://` / `postgresql://` is switched to the
  `postgresql+psycopg` async driver with SQLAlchemy's URL API. Query parameters such as
  `sslmode=require` and `channel_binding=require` pass through to libpq.
- One engine per process, created by the app factory and disposed on shutdown. Small
  pool (`pool_size=3`, `max_overflow=2`), `pool_pre_ping`, `pool_recycle=300s`,
  `connect_timeout=10s`, and `prepare_threshold=None` (safe behind Neon's PgBouncer).
- Settings hold URLs and keys as `SecretStr`. Engine logging is off, `hide_parameters`
  is on, driver error text is never returned to clients (503 `database_unavailable`).
- Startup never runs `create_all`; Alembic is the only schema writer.

## Testing strategy

- `tests/db_guard.py` resolves the database: `TEST_DATABASE_URL` only, no fallback, and
  refused if it matches `DATABASE_URL` (same host, port, database and user).
- The session fixture runs `alembic upgrade head` on the test database (additive only).
- Each test gets one connection inside an outer transaction that is rolled back; API
  requests get a fresh session on that connection (savepoint mode), mirroring
  production's session-per-request.
- No test can reach an external service: real httpx transports are patched to raise,
  and Python-level socket connects and DNS lookups fail (except DNS for the test
  database host, which psycopg resolves in Python). Groq, Crossref and OpenAlex are
  exercised through `httpx.MockTransport` and recorded responses in `tests/fixtures/`.

## Observability

JSON logs on stdout. Every request gets an ID (or keeps a well-formed incoming
`X-Request-ID`), which is returned in the `X-Request-ID` header and in every error
body. The access log records method, path, status and duration — not query strings or
bodies. Exceptions are logged by class only, since driver messages can contain hosts or
SQL. Draft text and paper content are not logged.

## Security notes

- Secrets only via environment / gitignored `.env`; `.env.example` holds placeholders.
- CORS restricted to configured origins; credentials disabled.
- Input limits: draft text capped by `MAX_DRAFT_CHARS` (default 20,000) plus a hard parse
  cap; notes 5,000 chars; revised claims 2,000. Validation errors never echo input.
- CSV export neutralizes formula injection (cells starting with `= + - @`, tab or CR,
  including after leading whitespace, are prefixed with `'`); filenames are slugified.
- LLM output is validated against Pydantic schemas before use and is stored and returned
  as plain text. Prompts and drafts are never logged.

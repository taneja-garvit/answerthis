# Evidence Review Workspace

Evidence Review Workspace is a product-engineering prototype for human-in-the-loop
review of scientific claims.

AI-assisted research tools can identify potential citation and evidence mismatches,
but researchers still need to inspect evidence, make judgment calls, and preserve
those decisions for collaborators. This prototype explores a structured review
workflow where each claim is paired with its evidence, AI assessment, human
decision, reviewer note, and audit history.

> **AI assists. Human decides.** An AI assessment is a suggestion for review. It is
> never presented as scientific truth, and a claim is only "reviewed" once a person
> records a decision.

## Context

The idea came from evaluating AnswerThis, an AI research
platform that already performs citation checking and reasons about whether claims
are supported by cited research. This project does **not** replace a citation
checker. It explores the workflow layer around claim verification — think "pull-request
review, but for the claims in a research draft". It is an independent prototype, not
an AnswerThis feature.

```
Research draft → claims → sources → evidence → AI assessment
      → human decision + note → persisted review state → CSV / JSON audit trail
```

## Status

| Phase | Scope | State |
|---|---|---|
| 1 — Foundation | config, Neon/Postgres, models, Alembic, error format, health, projects, drafts | done |
| 2 — Review domain | claims, evidence, assessments, reviews + history, progress, audit, export, seeded demo | done |
| 3 — AI pipeline | claim extraction, citation resolution, retrieval, assessment, evaluation | done |
| 4 — Frontend | review workspace UI | done |
| 5 — Polish | integration, screenshots, final evaluation | done |

Live AI runs through Groq (`LLM_PROVIDER=groq`). Without a key, the deterministic
provider is used: it reproduces the seeded demo's hand-authored fixtures and returns
`UNVERIFIABLE` ("no live AI assessment was run") for anything else. The seeded demo's
assessments are stored with `provider = "demo_fixture"` and `live_model = false`.

## Architecture

```
backend/
  app/
    main.py            app factory (CORS, request IDs, error envelope)
    api/routes/        thin FastAPI routes
    services/          domain logic and the analysis pipeline; owns transactions
    ai/                LLM interface, structured output, prompts, Groq + deterministic providers
    papers/            Crossref and OpenAlex metadata providers
    repositories/      non-trivial queries (composite claim loading)
    models/            SQLAlchemy 2 models
    schemas/           Pydantic v2 request/response models
    db/                engine + session (one engine per process)
    seed/              seeded heart-failure demo + verified paper fixture
  alembic/             migrations (source of truth for the schema)
  tests/               pytest suite (isolated TEST_DATABASE_URL only, no network)
  eval/                evaluation dataset, label review CLI, runner
docs/                  architecture, product, API, manual requests
scripts/demo_flow.sh   curl walkthrough of the demo
```

Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2 (async) with psycopg 3, Alembic,
PostgreSQL on [Neon](https://neon.tech). See [docs/architecture.md](docs/architecture.md).

## Setup

### 1. Neon databases

Neon is the primary database; no local PostgreSQL or Docker is required.

1. Create a Neon project (any region). Its default branch (`main`) is the
   **development** database.
2. Create a second branch for tests, e.g. `test` (Console → Branches → New branch,
   or `neon branches create --name test`). A branch is an isolated copy with its own
   compute endpoint and hostname, so tests can never touch development data.
3. From **Connection Details**, copy the connection string for each branch. Use the
   direct (non-pooled) string for both. If you later use the pooled `-pooler` host
   for the app, it still works: server-side prepared statements are disabled for
   PgBouncer compatibility. Keep running Alembic over the direct connection.

### 2. Environment

```bash
cp .env.example .env
```

Fill in `.env` (repository root; gitignored):

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | Neon dev branch. `postgresql://…?sslmode=require` as copied from Neon; the app selects the async psycopg driver itself. |
| `TEST_DATABASE_URL` | for tests | Neon test branch. Tests fail with an explicit message if missing, and refuse to run if it resolves to the same database as `DATABASE_URL`. |
| `LLM_PROVIDER` | no | `deterministic` (default, no key) or `groq`. With `groq`, both `GROQ_API_KEY` and `LLM_MODEL` are required; startup fails with a clear error otherwise. |
| `GROQ_API_KEY`, `LLM_MODEL` | only for `groq` | No model is hard-coded; `LLM_MODEL` picks the live model. |
| `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES` | no | Default 60 s / 2. Retries are bounded, for rate limits and timeouts and for invalid structured output alike. |
| `CONTACT_EMAIL` | no | Optional. Sent as `mailto` to Crossref and OpenAlex, which give better service to requests that identify a contact (their "polite pool"). Leave blank to omit. |
| `OPENALEX_API_KEY` | no | Optional. |
| `HTTP_TIMEOUT_SECONDS`, `HTTP_MAX_RETRIES`, `PAPER_CACHE_TTL_DAYS` | no | Metadata provider timeouts and retries (10 s / 2) and DOI cache lifetime (30 days). |
| `CORS_ORIGINS` | no | Default `http://localhost:5173`. |
| `MAX_DRAFT_CHARS` | no | Default 20000. |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_CONNECT_TIMEOUT_SECONDS` | no | Small defaults (3 / 2 / 10 s) suited to a serverless database. |

Connection strings are held as secrets in settings and are never logged or returned
in error responses.

### 3. Live AI with Groq (optional)

1. Create an API key at console.groq.com (the free tier works; it is rate-limited).
2. In `.env`: `LLM_PROVIDER=groq`, `GROQ_API_KEY=<your key>`, and `LLM_MODEL=<a Groq chat
   model that supports JSON mode>`, chosen from Groq's current model list. Larger models
   follow the assessment rules more reliably.
3. Restart the API. The key is held as a secret and is never logged or returned.

Without these settings everything runs offline on the deterministic provider. Tests
always use the deterministic or a fake provider and never call Groq.

### 4. Backend

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

### 5. Migrations

The application never creates or alters tables on startup; Alembic does.

```bash
cd backend
.venv/bin/alembic upgrade head     # apply migrations to DATABASE_URL
.venv/bin/alembic current          # show the applied revision
.venv/bin/alembic history          # list revisions
```

The test suite applies migrations to `TEST_DATABASE_URL` itself.

### 6. Run the API

```bash
cd backend
.venv/bin/uvicorn app.main:create_app --factory --reload --port 8000
```

Interactive docs: http://localhost:8000/docs

### 7. Seeded demo

```bash
cd backend
.venv/bin/python -m app.seed.demo          # create if missing (idempotent)
.venv/bin/python -m app.seed.demo --reset  # delete and recreate (clears its reviews)
```

or `POST /api/demo` (`?reset=true` to recreate). Re-running never duplicates the
demo project and keeps any decisions already saved.

The demo cites De Lathauwer et al., *Remote Patient Monitoring in Heart Failure: A
Comprehensive Meta-Analysis of Effective Programme Components for Hospitalization and
Mortality Reduction*, European Journal of Heart Failure 27(9):1670–1685, 2025,
[doi:10.1002/ejhf.3568](https://doi.org/10.1002/ejhf.3568). Metadata and abstract were
retrieved from the Crossref and OpenAlex public APIs; the abstract is reproduced
verbatim under the article's CC BY-NC-ND 4.0 licence. Every evidence passage is an
exact sentence of that public abstract (enforced by tests). The article is open access,
but only the abstract is ingested, so evidence is labelled `ABSTRACT`. No synthetic
evidence is used.

| # | Draft claim | Fixture AI assessment |
|---|---|---|
| 1 | …associated with lower odds of first HF hospitalization (pooled OR 0.78) | `SUPPORTED` |
| 2 | …lowered the odds of death by 22% | `PARTIALLY_SUPPORTED` — `FIGURE_MISMATCH` (source: OR 0.81 ≈ 19%) |
| 3 | …works for every heart-failure patient | `UNSUPPORTED` — `OVERGENERALIZATION`, `WORDING_STRENGTH` |

### 8. Analyze a draft

```bash
# create a project and a draft, then run the pipeline (synchronous)
PROJECT=$(curl -s -X POST localhost:8000/api/projects -H 'Content-Type: application/json' \
  -d '{"title":"My review"}' | jq -r .id)
DRAFT=$(curl -s -X POST localhost:8000/api/projects/$PROJECT/drafts -H 'Content-Type: application/json' \
  --data-binary @- <<'JSON' | jq -r .id
{"original_text": "Non-invasive remote patient monitoring was associated with lower odds of first heart-failure hospitalization (OR 0.78) [1]. It lowered the odds of death by 22% [1]. It works for every heart-failure patient [1].\n\n[1] De Lathauwer ILJ, et al. Remote patient monitoring in heart failure. Eur J Heart Fail. 2025. doi:10.1002/ejhf.3568"}
JSON
)
curl -s -X POST localhost:8000/api/drafts/$DRAFT/analyze | jq '{claims_extracted, claims_assessed, llm_calls}'
```

Pipeline: deterministic segmentation and citation parsing → claim extraction (LLM) → DOI
resolution (cache, then Crossref and OpenAlex) → evidence retrieval from the public
abstract → assessment (LLM, or a rule-based `UNVERIFIABLE` when there is nothing to
compare against) → persisted. Analyzing again is safe: assessed claims are reused without
LLM calls. `POST /api/claims/{id}/assess` re-assesses one claim and appends to its
history. Details: [docs/architecture.md](docs/architecture.md#ai-pipeline),
[docs/api.md](docs/api.md#analyze-a-draft).


## Frontend

React 19 + Vite + TypeScript (strict), Tailwind CSS v4 design tokens, TanStack Query
for server state, React Router (URL holds the selected claim), lucide icons, Inter
(bundled, no external font requests).

```bash
cd frontend
npm install
cp .env.example .env.local      # optional; VITE_API_BASE_URL defaults to http://localhost:8000
npm run dev                     # http://localhost:5173 (strict port: the API's CORS allows exactly this origin)
npm test                        # Vitest + Testing Library + MSW (no backend needed)
npm run build
```

Screens: **draft input** (`/`) → **review workspace** (`/review/:projectId?claim=…`) →
**review complete** (`/review/:projectId/complete`). "Load example" fills the editor with
the heart-failure draft; "Analyze draft" runs the live pipeline.

## Tests

```bash
cd backend
.venv/bin/pytest
```

- Database tests run **only** against `TEST_DATABASE_URL`, never `DATABASE_URL`.
- Each test runs in a transaction that is rolled back, so tests leave no rows behind.
  Test setup never drops or truncates tables.
- Outbound network access is blocked during tests (httpx transports and Python sockets);
  Groq, Crossref and OpenAlex are exercised through mocks and recorded responses.
- Pure unit tests (config, CSV safety, the test-DB guard) run without a database.

## Live validation

A controlled smoke test of the full live pipeline, run once on 2026-10-19:

- **Setup:** the three-claim heart-failure draft (doi:10.1002/ejhf.3568) through
  `POST /api/drafts/{id}/analyze`, with `LLM_PROVIDER=groq`,
  `LLM_MODEL=openai/gpt-oss-120b`, live Crossref and OpenAlex, and the Neon dev database.
- **Calls:** 4 Groq calls on the first analysis (1 extraction + 3 assessments), each valid
  on the first attempt. Crossref and OpenAlex were each called once.
- **Results:** expected classifications, written before the run, matched the actual
  ones:

  | Claim | Expected | Actual |
  |---|---|---|
  | OR 0.78 hospitalization | SUPPORTED | SUPPORTED |
  | "lowered the odds of death by 22%" | PARTIALLY_SUPPORTED or UNSUPPORTED + FIGURE_MISMATCH | PARTIALLY_SUPPORTED + FIGURE_MISMATCH (OR 0.81 ≈ 19%) |
  | "works for every heart-failure patient" | UNSUPPORTED + OVERGENERALIZATION / WORDING_STRENGTH | UNSUPPORTED + OVERGENERALIZATION |

- **Persistence:** claims, sources, evidence and assessments were stored correctly.
  Analyzing the unchanged draft again made 0 LLM calls and created no duplicates.
- **Observed weaknesses:** for the "every patient" claim, retrieval did not surface the
  abstract's most relevant scope sentences (study count, heterogeneity), although the
  verdict was still correct. One suggested revision was worded more causally than the
  results sentence. Suggestions are shown as unverified for this reason.

This is a smoke test on three claims from one paper, **not** a general accuracy
benchmark. See [docs/evaluation.md](docs/evaluation.md) for how accuracy is to be
measured.

## Evaluation

`backend/eval/` holds 30 claim/evidence pairs (13 from the demo paper's public abstract,
17 clearly marked synthetic), a label-review CLI, and a runner that computes verdict
accuracy and precision, recall and F1 for problematic-claim detection. **All labels are
pending human review, so there are no official metrics yet.** See
[docs/evaluation.md](docs/evaluation.md).

## Limitations (current)

- Evidence is abstract-only. Open-access full text is linked but not fetched or parsed,
  and user-provided source text is not supported yet. Claims whose support lies outside
  the abstract come out `UNVERIFIABLE` or under-supported.
- Retrieval is lexical (BM25 with number-aware boosts). Paraphrases that share no words
  with the source can be missed.
- Citation parsing covers `[1]`, `[1, 2]`, `[1-3]`, DOIs and DOI URLs, with a numbered
  reference list. Author–year styles (Smith 2020) are not resolved.
- Analysis is synchronous. Each claim costs one LLM call, so long drafts take a while and
  free-tier rate limits apply. Claims that hit a limit are marked `ERROR` and retried on
  the next analyze call.
- LLM assessments are suggestions. They can be wrong (see the live-test notes), and the
  confidence level is the model's own coarse estimate, not a calibrated probability.
- Evaluation labels have not yet been reviewed by a person.
- No authentication, teams, or real-time collaboration (out of scope for the MVP).
- An AI assessment, when present, is a suggestion. It does not establish whether a
  claim is scientifically true.

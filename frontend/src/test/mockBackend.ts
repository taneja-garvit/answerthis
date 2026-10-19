/** In-memory stand-in for the FastAPI backend, served through MSW so tests
 *  exercise the real typed API client. Shapes match backend/app/schemas. */
import { delay, http, HttpResponse, type HttpHandler } from "msw";

import { API_BASE_URL } from "../api/client";
import type { AnalysisResult, Claim, Draft, Progress, Project, ReviewInput } from "../api/types";
import recorded from "./fixtures/heartFailureClaims.json";

const api = (path: string) => `${API_BASE_URL}${path}`;
const clone = <T,>(value: T): T => structuredClone(value);
export const liveClaims = recorded.claims as unknown as Claim[];

type Failure = { status: number; code: string; message?: string };
const errorResponse = ({ status, code, message = "failed" }: Failure) =>
  HttpResponse.json({ error: { code, message, request_id: "req-test-1" } }, { status });

export interface MockBackendOptions {
  /** Claims returned by analyze (defaults to the recorded live run). */
  claims?: Claim[];
  /** Start with an existing, analyzed project (for workspace tests). */
  seeded?: boolean;
}

export function createMockBackend(options: MockBackendOptions = {}) {
  const projectId = "proj-1";
  const draftId = "draft-1";
  const template = clone(options.claims ?? liveClaims).map((c) => ({ ...c, project_id: projectId, draft_id: draftId }));
  const state = {
    project: null as Project | null,
    draft: null as Draft | null,
    claims: [] as Claim[],
    calls: { createProject: 0, createDraft: 0, analyze: 0, saveReview: [] as { claimId: string; body: ReviewInput }[], reassess: 0, exports: [] as string[] },
    /** Inject failures or latency per operation. */
    analyzeFailure: null as Failure | null,
    analyzeDelayMs: 0,
    saveFailures: new Map<string, Failure>(),
    saveDelayMs: 0,
    reassessFailure: null as Failure | null,
    reassessResult: null as ((claim: Claim) => Claim) | null,
    exportFailure: null as Failure | null,
  };

  const now = () => new Date("2026-10-19T12:00:00Z").toISOString();
  const makeProject = (title: string): Project => ({
    id: projectId, title, description: null, status: "ACTIVE", is_demo: false, drafts: [], created_at: now(), updated_at: now(),
  });
  const projectView = (): Project => ({
    ...state.project!,
    drafts: state.draft
      ? [{ id: state.draft.id, char_count: state.draft.char_count, claim_count: state.claims.length, analysis_status: state.draft.analysis_status, created_at: now() }]
      : [],
  });

  if (options.seeded) {
    state.project = makeProject("Heart-failure review");
    state.draft = { id: draftId, project_id: projectId, original_text: "…", char_count: 1, analysis_status: "ANALYZED", analyzed_at: now(), created_at: now(), updated_at: now() };
    state.claims = clone(template);
  }

  const progress = (): Progress => {
    const decisions = { KEEP: 0, QUALIFY: 0, REPLACE: 0, REMOVE: 0 };
    const verdicts = { SUPPORTED: 0, PARTIALLY_SUPPORTED: 0, UNSUPPORTED: 0, UNVERIFIABLE: 0, NOT_ASSESSED: 0 };
    for (const c of state.claims) {
      if (c.review) decisions[c.review.decision] += 1;
      verdicts[c.assessment?.verdict ?? "NOT_ASSESSED"] += 1;
    }
    const reviewed = Object.values(decisions).reduce((a, b) => a + b, 0);
    const total = state.claims.length;
    return {
      project_id: projectId, total_claims: total, reviewed_claims: reviewed, remaining_claims: total - reviewed,
      completion_percentage: total ? Math.round((reviewed / total) * 1000) / 10 : 0, is_complete: total > 0 && reviewed === total,
      human_decisions: decisions, ai_verdicts: verdicts,
    };
  };

  const findClaim = (id: string) => state.claims.find((c) => c.id === id);

  const handlers: HttpHandler[] = [
    http.post(api("/api/projects"), async ({ request }) => {
      state.calls.createProject += 1;
      const { title } = (await request.json()) as { title: string };
      state.project = makeProject(title);
      return HttpResponse.json(state.project, { status: 201 });
    }),
    http.get(api("/api/projects/:id"), ({ params }) =>
      state.project && params.id === projectId ? HttpResponse.json(projectView()) : errorResponse({ status: 404, code: "not_found", message: "Project not found" }),
    ),
    http.post(api("/api/projects/:id/drafts"), async ({ request }) => {
      state.calls.createDraft += 1;
      const { original_text } = (await request.json()) as { original_text: string };
      state.draft = { id: draftId, project_id: projectId, original_text, char_count: original_text.length, analysis_status: "NOT_ANALYZED", analyzed_at: null, created_at: now(), updated_at: now() };
      return HttpResponse.json(state.draft, { status: 201 });
    }),
    http.post(api("/api/drafts/:id/analyze"), async () => {
      state.calls.analyze += 1;
      if (state.analyzeDelayMs) await delay(state.analyzeDelayMs);
      if (state.analyzeFailure) {
        state.draft!.analysis_status = "FAILED";
        return errorResponse(state.analyzeFailure);
      }
      state.claims = clone(template);
      state.draft!.analysis_status = "ANALYZED";
      const result: AnalysisResult = {
        draft_id: draftId, project_id: projectId, analysis_status: "ANALYZED", rerun: false,
        claims_extracted: state.claims.length, claims_processed: state.claims.length, claims_reused: 0,
        claims_assessed: state.claims.filter((c) => c.assessment).length,
        claims_unverifiable: state.claims.filter((c) => c.assessment?.verdict === "UNVERIFIABLE").length,
        claims_failed: state.claims.filter((c) => c.status === "ERROR").length,
        llm_provider: "groq", llm_model: "test-model", llm_calls: 4, claims: clone(state.claims),
      };
      return HttpResponse.json(result);
    }),
    http.get(api("/api/drafts/:id/claims"), () =>
      HttpResponse.json({ draft_id: draftId, project_id: projectId, claims: clone(state.claims) }),
    ),
    http.get(api("/api/claims/:id"), ({ params }) => {
      const claim = findClaim(String(params.id));
      return claim ? HttpResponse.json(clone(claim)) : errorResponse({ status: 404, code: "not_found" });
    }),
    http.put(api("/api/claims/:id/review"), async ({ params, request }) => {
      const claimId = String(params.id);
      const body = (await request.json()) as ReviewInput;
      state.calls.saveReview.push({ claimId, body });
      if (state.saveDelayMs) await delay(state.saveDelayMs);
      const failure = state.saveFailures.get(claimId);
      if (failure) return errorResponse(failure);
      if (body.decision === "REPLACE" && !body.revised_claim) {
        return errorResponse({ status: 422, code: "validation_error", message: "revised_claim is required" });
      }
      const claim = findClaim(claimId);
      if (!claim) return errorResponse({ status: 404, code: "not_found" });
      const at = new Date().toISOString();
      claim.review = {
        id: claim.review?.id ?? `review-${claimId}`, decision: body.decision, reviewer_note: body.reviewer_note,
        revised_claim: body.revised_claim, reviewed_at: at, created_at: claim.review?.created_at ?? at, updated_at: at,
      };
      claim.review_status = "REVIEWED";
      return HttpResponse.json(clone(claim));
    }),
    http.post(api("/api/claims/:id/assess"), ({ params }) => {
      state.calls.reassess += 1;
      const claim = findClaim(String(params.id));
      if (!claim) return errorResponse({ status: 404, code: "not_found" });
      if (state.reassessFailure) {
        claim.processing_error = "Latest reassessment failed: The AI provider's rate limit was reached.";
        return errorResponse(state.reassessFailure);
      }
      const updated = state.reassessResult ? state.reassessResult(clone(claim)) : claim;
      Object.assign(claim, updated, { processing_error: null, status: "READY" });
      return HttpResponse.json(clone(claim));
    }),
    http.get(api("/api/projects/:id/progress"), () => HttpResponse.json(progress())),
    http.get(api("/api/projects/:id/export"), ({ request }) => {
      const format = new URL(request.url).searchParams.get("format") ?? "csv";
      state.calls.exports.push(format);
      if (state.exportFailure) return errorResponse(state.exportFailure);
      return new HttpResponse(format === "csv" ? "claim_number\n1\n" : "{}", {
        headers: {
          "Content-Type": format === "csv" ? "text/csv" : "application/json",
          "Content-Disposition": `attachment; filename="evidence-review-heart-failure-20261019.${format}"`,
        },
      });
    }),
  ];

  return { state, handlers, projectId, draftId };
}

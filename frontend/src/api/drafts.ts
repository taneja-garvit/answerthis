import { apiRequest } from "./client";
import type { AnalysisResult, Draft, DraftClaims } from "./types";

export const createDraft = (projectId: string, originalText: string) =>
  apiRequest<Draft>(`/api/projects/${projectId}/drafts`, {
    method: "POST",
    body: { original_text: originalText },
  });

/** Synchronous on the server: typically 30–60 s for a short draft. */
export const analyzeDraft = (draftId: string, signal?: AbortSignal) =>
  apiRequest<AnalysisResult>(`/api/drafts/${draftId}/analyze`, { method: "POST", body: {}, signal });

export const getDraftClaims = (draftId: string, signal?: AbortSignal) =>
  apiRequest<DraftClaims>(`/api/drafts/${draftId}/claims`, { signal });

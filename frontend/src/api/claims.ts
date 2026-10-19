import { apiRequest } from "./client";
import type { Claim } from "./types";

export const getClaim = (claimId: string) => apiRequest<Claim>(`/api/claims/${claimId}`);

/** Appends a new AI assessment; an existing human review is kept. */
export const reassessClaim = (claimId: string) =>
  apiRequest<Claim>(`/api/claims/${claimId}/assess`, { method: "POST", body: {} });

import { apiRequest } from "./client";
import type { Claim, ReviewInput } from "./types";

export const saveReview = (claimId: string, input: ReviewInput) =>
  apiRequest<Claim>(`/api/claims/${claimId}/review`, { method: "PUT", body: input });

import type { Claim } from "../../api/types";
import { NEEDS_ATTENTION } from "../../lib/labels";

export type ClaimFilter = "all" | "needs_review" | "reviewed" | "attention";

export const FILTERS: { id: ClaimFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "needs_review", label: "Needs review" },
  { id: "reviewed", label: "Reviewed" },
  { id: "attention", label: "Needs attention" },
];

export function matchesFilter(claim: Claim, filter: ClaimFilter): boolean {
  switch (filter) {
    case "all":
      return true;
    case "needs_review":
      return claim.review_status === "NEEDS_REVIEW";
    case "reviewed":
      return claim.review_status === "REVIEWED";
    case "attention":
      return (
        claim.status === "ERROR" ||
        claim.assessment === null ||
        NEEDS_ATTENTION.includes(claim.assessment.verdict)
      );
  }
}

/** Next claim needing review after `currentId`, wrapping around; skips claims
 *  whose save is in flight. */
export function nextUnreviewed(claims: Claim[], currentId: string, skip: Set<string>): Claim | undefined {
  const start = claims.findIndex((c) => c.id === currentId);
  const ordered = [...claims.slice(start + 1), ...claims.slice(0, Math.max(start, 0))];
  return ordered.find((c) => c.review_status === "NEEDS_REVIEW" && c.id !== currentId && !skip.has(c.id));
}

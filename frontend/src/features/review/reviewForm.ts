import type { Claim, ReviewDecision, ReviewInput } from "../../api/types";

export interface ReviewFormValues {
  decision: ReviewDecision | null;
  note: string;
  revised: string;
}

export function savedValues(claim: Claim): ReviewFormValues {
  return {
    decision: claim.review?.decision ?? null,
    note: claim.review?.reviewer_note ?? "",
    revised: claim.review?.revised_claim ?? "",
  };
}

export const revisionApplies = (decision: ReviewDecision | null) =>
  decision === "QUALIFY" || decision === "REPLACE";

export function isDirty(values: ReviewFormValues, claim: Claim): boolean {
  const saved = savedValues(claim);
  const revisedChanged = revisionApplies(values.decision) && values.revised.trim() !== saved.revised.trim();
  return (
    values.decision !== saved.decision || values.note.trim() !== saved.note.trim() || revisedChanged
  );
}

export function validationError(values: ReviewFormValues): string | null {
  if (!values.decision) return "Choose a decision.";
  if (values.decision === "REPLACE" && !values.revised.trim()) {
    return "Replace needs the replacement wording.";
  }
  return null;
}

export function toReviewInput(values: ReviewFormValues): ReviewInput {
  if (!values.decision) throw new Error("decision required");
  return {
    decision: values.decision,
    reviewer_note: values.note.trim() || null,
    // The API rejects a revision on KEEP/REMOVE; it is kept locally in case the
    // reviewer switches back to Qualify/Replace.
    revised_claim: revisionApplies(values.decision) ? values.revised.trim() || null : null,
  };
}

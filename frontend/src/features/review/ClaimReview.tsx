import { ArrowRight, Check, RefreshCw } from "lucide-react";
import { useEffect, useId, useState, type ReactNode } from "react";

import type { Claim, ReviewDecision } from "../../api/types";
import { Button } from "../../components/Button";
import { InlineError } from "../../components/InlineError";
import type { UserFacingError } from "../../lib/errors";
import { DECISIONS } from "../../lib/labels";
import { formatTime } from "../../lib/format";
import { AssessmentSummary } from "./AssessmentSummary";
import { ClaimErrorState } from "./ClaimErrorState";
import { DecisionSelector } from "./DecisionSelector";
import { IssueCard } from "./IssueCard";
import { isDirty, revisionApplies, validationError, type ReviewFormValues } from "./reviewForm";
import { SuggestedRevision } from "./SuggestedRevision";
import type { SaveState } from "./useClaimSaves";

interface ClaimReviewProps {
  claim: Claim;
  position: number;
  total: number;
  values: ReviewFormValues;
  onChange: (values: ReviewFormValues) => void;
  saveState: SaveState | undefined;
  onSave: () => void;
  onSaveNext: () => void;
  hasNext: boolean;
  reassessing: boolean;
  reassessError: UserFacingError | null;
  onReassess: () => void;
}

const normalize = (text: string) => text.replace(/\s*\[[\d,\s–-]+\]/g, "").replace(/\s+/g, " ").trim();

export function ClaimReview({
  claim,
  position,
  total,
  values,
  onChange,
  saveState,
  onSave,
  onSaveNext,
  hasNext,
  reassessing,
  reassessError,
  onReassess,
}: ClaimReviewProps) {
  const helpId = useId();
  const revisedId = useId();
  const noteId = useId();
  const assessment = claim.assessment;
  const saving = saveState?.status === "saving";
  const dirty = isDirty(values, claim);
  const invalid = validationError(values);
  const showRevision = revisionApplies(values.decision);
  const revisionRequired = values.decision === "REPLACE";
  const failed = claim.status === "ERROR" && !assessment;
  const sentenceDiffers = normalize(claim.original_sentence) !== normalize(claim.claim_text);
  const set = (patch: Partial<ReviewFormValues>) => onChange({ ...values, ...patch });

  // Focus the revised claim right after it renders with the suggestion, before
  // any further input (a deferred focus could steal keystrokes meant elsewhere).
  const [focusRevised, setFocusRevised] = useState(false);
  useEffect(() => {
    if (!focusRevised) return;
    document.getElementById(revisedId)?.focus();
    setFocusRevised(false);
  }, [focusRevised, revisedId]);

  const useSuggestion = () => {
    if (!assessment?.suggested_revision) return;
    set({ revised: assessment.suggested_revision, decision: values.decision ?? "QUALIFY" });
    setFocusRevised(true);
  };

  const canSave = Boolean(values.decision) && !invalid && !saving && (dirty || !claim.review);
  const moveOnly = !dirty && Boolean(claim.review) && hasNext;

  return (
    <article aria-labelledby="claim-heading" className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 scroll-pb-8 overflow-y-auto overflow-x-hidden">
        <div className="mx-auto max-w-[46rem] px-6 pt-7 pb-16 lg:px-8">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-baseline gap-1.5 text-sm text-ink-3">
              <h2 id="claim-heading" className="font-medium text-ink-2">
                Claim {position} of {total}
              </h2>
              {claim.citation_marker && <span>· Cites {claim.citation_marker}</span>}
            </div>
            {!failed && (
              <Button
                size="sm"
                variant="ghost"
                onClick={onReassess}
                loading={reassessing}
                icon={<RefreshCw className="size-3.5" aria-hidden />}
              >
                {reassessing ? "Reassessing…" : "Reassess"}
              </Button>
            )}
          </div>

          <blockquote className="text-wrap-anywhere mt-3 text-xl font-medium tracking-[-0.005em] text-ink">
            {claim.claim_text}
          </blockquote>
          {sentenceDiffers && (
            <p className="mt-2 text-sm text-ink-3">
              In your draft: <span className="text-wrap-anywhere text-ink-2">“{claim.original_sentence}”</span>
            </p>
          )}

          <div className="mt-7 space-y-5">
            {reassessError && (
              <InlineError title="Reassessment didn't complete" error={reassessError} />
            )}
            {claim.processing_error && assessment && !reassessError && (
              <p role="status" className="rounded-md border border-partial-line bg-partial-soft px-3 py-2 text-sm text-ink-2">
                {claim.processing_error} The assessment below is the most recent one that completed.
              </p>
            )}

            {failed && <ClaimErrorState message={claim.processing_error} onRetry={onReassess} retrying={reassessing} />}
            {assessment && <AssessmentSummary assessment={assessment} busy={reassessing} />}

            {assessment && assessment.issues.length > 0 && (
              <section aria-labelledby="issues-heading">
                <h3 id="issues-heading" className="text-sm font-semibold text-ink-2">
                  Issues detected <span className="font-normal text-ink-3">· {assessment.issues.length}</span>
                </h3>
                <ul className="mt-2.5 space-y-2.5">
                  {assessment.issues.map((issue, i) => (
                    <IssueCard key={`${issue.type}-${i}`} issue={issue} />
                  ))}
                </ul>
              </section>
            )}
            {assessment && assessment.issues.length === 0 && (
              <p className="flex items-center gap-2 text-sm text-ink-2">
                <Check className="size-4 text-supported" aria-hidden /> No issues detected in the evidence shown.
              </p>
            )}

            {assessment?.suggested_revision && (
              <SuggestedRevision text={assessment.suggested_revision} onUse={useSuggestion} disabled={saving} />
            )}
          </div>

          <section aria-labelledby="decision-heading" className="mt-8 border-t border-line pt-6">
            <h3 id="decision-heading" className="text-md font-semibold">
              Your decision
            </h3>
            <div className="mt-3">
              <DecisionSelector
                value={values.decision}
                onChange={(decision: ReviewDecision) => set({ decision })}
                disabled={saving}
                describedBy={helpId}
              />
            </div>
            <p id={helpId} className="mt-2 text-sm text-ink-3">
              {values.decision ? DECISIONS[values.decision].help : "Choose how this claim should be handled. The AI assessment does not choose for you."}
            </p>

            {showRevision && (
              <div className="mt-5">
                <label htmlFor={revisedId} className="flex items-baseline justify-between text-base font-medium">
                  Revised claim
                  <span className="text-sm font-normal text-ink-3">{revisionRequired ? "Required" : "Optional"}</span>
                </label>
                <textarea
                  id={revisedId}
                  value={values.revised}
                  onChange={(e) => set({ revised: e.target.value })}
                  disabled={saving}
                  rows={3}
                  aria-required={revisionRequired}
                  aria-invalid={(revisionRequired && !values.revised.trim()) || undefined}
                  aria-describedby={revisionRequired && !values.revised.trim() ? `${revisedId}-error` : undefined}
                  placeholder={revisionRequired ? "Write the replacement claim…" : "Narrowed or corrected wording…"}
                  className="mt-1.5 block w-full resize-y rounded-md border border-line-strong bg-surface px-3 py-2 text-md leading-6 placeholder:text-ink-3 focus:border-accent focus:outline-none disabled:opacity-60"
                />
                {revisionRequired && !values.revised.trim() && (
                  <p id={`${revisedId}-error`} className="mt-1.5 text-sm text-danger">
                    Replace needs the replacement wording.
                  </p>
                )}
              </div>
            )}

            <div className="mt-5">
              <label htmlFor={noteId} className="flex items-baseline justify-between text-base font-medium">
                Reviewer note
                <span className="text-sm font-normal text-ink-3">Optional</span>
              </label>
              <textarea
                id={noteId}
                value={values.note}
                onChange={(e) => set({ note: e.target.value })}
                disabled={saving}
                rows={3}
                maxLength={5000}
                placeholder="Why did you make this decision?"
                className="mt-1.5 block w-full resize-y rounded-md border border-line-strong bg-surface px-3 py-2 text-md leading-6 placeholder:text-ink-3 focus:border-accent focus:outline-none disabled:opacity-60"
              />
            </div>
          </section>
        </div>
      </div>

      <footer className="shrink-0 border-t border-line bg-surface px-6 py-3 shadow-[0_-1px_0_rgba(30,28,25,0.02),0_-6px_16px_-12px_rgba(30,28,25,0.18)] lg:px-8">
        <div className="mx-auto flex max-w-[46rem] flex-wrap items-center justify-end gap-x-3 gap-y-2">
          <SaveStatus claim={claim} dirty={dirty} saveState={saveState} />
          <Button variant="secondary" onClick={onSave} disabled={!canSave} loading={saving}>
            Save decision
          </Button>
          <Button
            variant="primary"
            onClick={onSaveNext}
            disabled={!(canSave || moveOnly)}
            icon={<ArrowRight className="size-4" aria-hidden />}
            className="flex-row-reverse"
          >
            {moveOnly ? "Next claim" : hasNext ? "Save & next" : "Save & finish"}
          </Button>
        </div>
      </footer>
    </article>
  );
}

function SaveStatus({ claim, dirty, saveState }: { claim: Claim; dirty: boolean; saveState: SaveState | undefined }) {
  let content: ReactNode = null;
  if (saveState?.status === "saving") content = "Saving…";
  else if (saveState?.status === "error") content = <span className="text-danger">{saveState.error.message}</span>;
  else if (dirty) content = "Unsaved changes";
  else if (claim.review) content = `Saved ${formatTime(claim.review.updated_at)}`;
  return (
    <p aria-live="polite" className="mr-auto min-w-0 text-sm text-ink-3">
      {content}
    </p>
  );
}

import type { Assessment } from "../../api/types";
import { VerdictBadge } from "../../components/VerdictBadge";
import { CONFIDENCE_LABELS } from "../../lib/labels";

/** The AI's view, deliberately set apart from the researcher's decision. */
export function AssessmentSummary({ assessment, busy }: { assessment: Assessment; busy: boolean }) {
  const ruleBased = assessment.confidence_level === null;
  return (
    <section aria-labelledby="ai-assessment" aria-busy={busy || undefined} className="rounded-lg border border-line bg-surface">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-t-lg border-b border-line bg-tint px-4 py-2.5">
        <h3 id="ai-assessment" className="section-label">
          AI assessment
        </h3>
        <VerdictBadge verdict={assessment.verdict} />
        <span className="text-sm text-ink-3">
          {ruleBased ? "No AI judgement: there was no evidence to compare" : CONFIDENCE_LABELS[assessment.confidence_level!]}
        </span>
        <span className="text-sm text-ink-3 sm:ml-auto">Based only on the evidence shown.</span>
      </div>
      <p className={`text-wrap-anywhere px-4 py-3 text-base leading-6 text-ink-2 ${busy ? "opacity-50" : ""}`}>
        {assessment.explanation}
      </p>
    </section>
  );
}

import { useEffect, useState } from "react";

import { Spinner } from "../../components/Spinner";
import { formatElapsed } from "../../lib/format";

const STEPS = [
  "Identifying the factual claims in your draft",
  "Resolving each citation to its published record",
  "Finding relevant passages in the source's public abstract",
  "Comparing each claim with that evidence",
];

/** Honest progress: the API does not report stages, so none are ticked off.
 *  Only elapsed time is shown. */
export function AnalysisLoading() {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const started = Date.now();
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <section
      aria-live="polite"
      aria-labelledby="analysis-title"
      className="rounded-lg border border-line bg-surface px-5 py-5"
    >
      <div className="flex items-start gap-3">
        <Spinner className="mt-0.5 size-4.5 text-accent" />
        <div className="flex-1">
          <div className="flex items-baseline justify-between gap-4">
            <h2 id="analysis-title" className="text-lg font-semibold">
              Analyzing your draft
            </h2>
            <span className="text-sm text-ink-3 tabular-nums" aria-label={`${elapsed} seconds elapsed`}>
              {formatElapsed(elapsed)}
            </span>
          </div>
          <p className="mt-1 text-ink-2">
            Extracting claims, resolving sources and checking evidence. This may take a moment while
            sources and evidence are checked.
          </p>
          <ul className="mt-4 space-y-1.5 border-t border-line pt-4 text-sm text-ink-2">
            {STEPS.map((step) => (
              <li key={step} className="flex items-center gap-2.5">
                <span aria-hidden className="size-1.5 rounded-full bg-line-strong" />
                {step}
              </li>
            ))}
          </ul>
          {elapsed >= 75 && (
            <p className="mt-4 text-sm text-ink-2">
              Still working. Longer drafts take more time; keep this page open.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

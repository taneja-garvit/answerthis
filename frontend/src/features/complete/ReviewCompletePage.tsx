import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, CircleCheck, Download } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useParams } from "react-router";

import { getProgress } from "../../api/projects";
import { queryKeys } from "../../api/queryKeys";
import type { Claim, Progress } from "../../api/types";
import { AppShell } from "../../components/AppShell";
import { Button } from "../../components/Button";
import { InlineError } from "../../components/InlineError";
import { Spinner } from "../../components/Spinner";
import { VerdictBadge } from "../../components/VerdictBadge";
import { toUserError } from "../../lib/errors";
import { DECISION_ORDER, DECISIONS, VERDICT_ORDER, VERDICTS } from "../../lib/labels";
import { pad2 } from "../../lib/format";
import { useExport } from "../export/useExport";
import { useWorkspaceData } from "../review/useWorkspaceData";

export function ReviewCompletePage() {
  const { projectId = "" } = useParams();
  const { project, claims } = useWorkspaceData(projectId);
  const progress = useQuery({
    queryKey: queryKeys.progress(projectId),
    queryFn: ({ signal }) => getProgress(projectId, signal),
  });

  let body: ReactNode;
  if (progress.isPending || project.isPending || claims.isPending) {
    body = (
      <div className="flex items-center gap-2 text-ink-2">
        <Spinner /> Loading summary…
      </div>
    );
  } else if (progress.isError || project.isError || claims.isError) {
    body = (
      <InlineError
        title="Couldn't load the summary"
        error={toUserError(progress.error ?? project.error ?? claims.error)}
        action={
          <Button size="sm" variant="secondary" onClick={() => void progress.refetch()}>
            Try again
          </Button>
        }
      />
    );
  } else if (!progress.data.is_complete) {
    body = (
      <div>
        <h1 className="text-xl font-semibold">Review in progress</h1>
        <p className="mt-2 text-ink-2">
          {progress.data.remaining_claims} of {progress.data.total_claims} claims still need a decision.
        </p>
        <ReturnLink projectId={projectId} />
      </div>
    );
  } else {
    body = <Summary projectId={projectId} progress={progress.data} claims={claims.data.claims} />;
  }

  return (
    <AppShell context={project.data?.title}>
      <div className="mx-auto max-w-3xl px-5 pt-12 pb-20 sm:px-6">{body}</div>
    </AppShell>
  );
}

function ReturnLink({ projectId }: { projectId: string }) {
  return (
    <Link
      to={`/review/${projectId}`}
      className="mt-6 inline-flex h-9 items-center gap-2 rounded-md border border-line-strong bg-surface px-3.5 font-medium text-ink hover:bg-subtle"
    >
      <ArrowLeft className="size-4" aria-hidden /> Return to review
    </Link>
  );
}

function Summary({ projectId, progress, claims }: { projectId: string; progress: Progress; claims: Claim[] }) {
  const exporter = useExport(projectId);
  return (
    <>
      <div className="flex items-center gap-2 text-accent">
        <CircleCheck className="size-5" aria-hidden />
        <span className="text-sm font-medium">All claims have a decision</span>
      </div>
      <h1 className="mt-2 text-xl font-semibold">Review complete</h1>
      <p className="mt-1 text-ink-2">
        {progress.reviewed_claims} of {progress.total_claims} claims reviewed. Review decisions remain editable.
      </p>

      <div className="mt-7 grid gap-3 sm:grid-cols-2">
        <section aria-labelledby="human-heading" className="rounded-lg border border-line bg-surface p-4">
          <h2 id="human-heading" className="section-label">
            Your decisions
          </h2>
          <ul className="mt-3 space-y-2">
            {DECISION_ORDER.map((decision) => {
              const meta = DECISIONS[decision];
              const Icon = meta.icon;
              return (
                <li key={decision} className="flex items-center gap-2.5">
                  <Icon className="size-4 text-accent" aria-hidden />
                  <span className="flex-1 text-ink">{meta.label}</span>
                  <span className="font-semibold tabular-nums">{progress.human_decisions[decision]}</span>
                </li>
              );
            })}
          </ul>
        </section>
        <section aria-labelledby="ai-heading" className="rounded-lg border border-line bg-tint p-4">
          <h2 id="ai-heading" className="section-label">
            AI assessments
          </h2>
          <ul className="mt-3 space-y-2">
            {VERDICT_ORDER.map((verdict) => {
              const meta = VERDICTS[verdict];
              const Icon = meta.icon;
              return (
                <li key={verdict} className="flex items-center gap-2.5">
                  <Icon className={`size-4 ${meta.tone.split(" ")[0]}`} aria-hidden />
                  <span className="flex-1 text-ink">{meta.label}</span>
                  <span className="font-semibold tabular-nums">{progress.ai_verdicts[verdict]}</span>
                </li>
              );
            })}
          </ul>
          {progress.ai_verdicts.NOT_ASSESSED > 0 && (
            <p className="mt-3 text-sm text-ink-3">{progress.ai_verdicts.NOT_ASSESSED} not assessed</p>
          )}
        </section>
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-2">
        <Button variant="primary" icon={<Download className="size-4" aria-hidden />} loading={exporter.isPending && exporter.variables === "csv"} onClick={() => exporter.mutate("csv")}>
          Export CSV
        </Button>
        <Button variant="secondary" icon={<Download className="size-4" aria-hidden />} loading={exporter.isPending && exporter.variables === "json"} onClick={() => exporter.mutate("json")}>
          Export JSON
        </Button>
        <Link to={`/review/${projectId}`} className="ml-auto inline-flex h-9 items-center gap-2 rounded-md px-3 font-medium text-ink-2 hover:bg-subtle hover:text-ink">
          <ArrowLeft className="size-4" aria-hidden /> Return to review
        </Link>
      </div>
      {exporter.isError && (
        <div className="mt-3">
          <InlineError title="Export failed" error={toUserError(exporter.error)} />
        </div>
      )}
      {exporter.isSuccess && (
        <p role="status" className="mt-3 text-sm text-ink-2">
          {exporter.data.toUpperCase()} audit trail downloaded.
        </p>
      )}

      <section aria-labelledby="decisions-heading" className="mt-10">
        <h2 id="decisions-heading" className="text-sm font-semibold text-ink-2">
          Claim by claim
        </h2>
        <ol className="mt-3 divide-y divide-line rounded-lg border border-line bg-surface">
          {claims.map((claim) => (
            <li key={claim.id} className="px-4 py-4">
              <div className="flex items-start gap-3">
                <span className="pt-0.5 text-sm font-semibold text-ink-3 tabular-nums">{pad2(claim.order)}</span>
                <div className="min-w-0 flex-1">
                  <p className={`text-wrap-anywhere ${claim.review?.decision === "REMOVE" ? "text-ink-3 line-through decoration-ink-3/60" : "text-ink"}`}>
                    {claim.claim_text}
                  </p>
                  {claim.review?.revised_claim && (
                    <p className="text-wrap-anywhere mt-1.5 border-l-2 border-accent-line pl-3 text-ink">{claim.review.revised_claim}</p>
                  )}
                  {claim.review?.reviewer_note && (
                    <p className="text-wrap-anywhere mt-1.5 text-sm text-ink-2">Note: {claim.review.reviewer_note}</p>
                  )}
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                    {claim.review && (
                      <span className="inline-flex h-5 items-center rounded-[4px] bg-accent px-1.5 font-medium text-white">
                        {DECISIONS[claim.review.decision].label}
                      </span>
                    )}
                    {claim.assessment && (
                      <>
                        <span className="text-ink-3">AI:</span>
                        <VerdictBadge verdict={claim.assessment.verdict} size="sm" />
                      </>
                    )}
                  </div>
                </div>
              </div>
            </li>
          ))}
        </ol>
      </section>
    </>
  );
}

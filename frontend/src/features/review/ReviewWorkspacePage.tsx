import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleAlert, CircleCheck, ListChecks, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useBlocker, useNavigate, useParams, useSearchParams } from "react-router";

import { ApiError } from "../../api/client";
import { analyzeDraft } from "../../api/drafts";
import { queryKeys } from "../../api/queryKeys";
import type { Claim, DraftClaims } from "../../api/types";
import { AppShell } from "../../components/AppShell";
import { Button } from "../../components/Button";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { InlineError } from "../../components/InlineError";
import { Spinner } from "../../components/Spinner";
import { toUserError } from "../../lib/errors";
import { EvidencePanel } from "../evidence/EvidencePanel";
import { ExportMenu } from "../export/ExportMenu";
import { ClaimReview } from "./ClaimReview";
import { ClaimSidebar } from "./ClaimSidebar";
import { nextUnreviewed, type ClaimFilter } from "./filters";
import { isDirty, savedValues, toReviewInput, validationError, type ReviewFormValues } from "./reviewForm";
import { useClaimSaves } from "./useClaimSaves";
import { useReassess } from "./useReassess";
import { useWorkspaceData } from "./useWorkspaceData";

export function ReviewWorkspacePage() {
  const { projectId = "" } = useParams();
  const { project, draft, claims } = useWorkspaceData(projectId);

  let body: ReactNode;
  if (project.isPending) body = <WorkspaceSkeleton />;
  else if (project.isError) {
    const notFound = project.error instanceof ApiError && project.error.status === 404;
    body = notFound ? (
      <CenteredMessage title="Review not found" text="This review doesn't exist, or its link is incomplete.">
        <Link to="/" className="font-medium text-accent underline-offset-4 hover:underline">
          Start a new review
        </Link>
      </CenteredMessage>
    ) : (
      <CenteredError title="Couldn't load this review" error={project.error} onRetry={() => project.refetch()} />
    );
  } else if (!draft) {
    body = (
      <CenteredMessage title="No draft in this review" text="Start a new review to analyze a draft.">
        <Link to="/" className="font-medium text-accent underline-offset-4 hover:underline">
          Start a new review
        </Link>
      </CenteredMessage>
    );
  } else if (draft.analysis_status === "ANALYZING") {
    body = (
      <CenteredMessage
        title="Analysis in progress"
        text="This draft is still being analyzed. The review will open here as soon as it finishes."
        icon={<Spinner className="size-5 text-accent" />}
      />
    );
  } else if (claims.isPending) body = <WorkspaceSkeleton />;
  else if (claims.isError) {
    body = <CenteredError title="Couldn't load the claims" error={claims.error} onRetry={() => claims.refetch()} />;
  } else if (claims.data.claims.length === 0) {
    body =
      draft.analysis_status === "ANALYZED" ? (
        <CenteredMessage
          title="No checkable claims found"
          text="The analysis didn't find factual claims with citations to review in this draft."
        >
          <Link to="/" className="font-medium text-accent underline-offset-4 hover:underline">
            Review another draft
          </Link>
        </CenteredMessage>
      ) : (
        <ReanalyzePrompt draftId={draft.id} projectId={projectId} />
      );
  } else {
    body = <Workspace projectId={projectId} draftId={draft.id} claims={claims.data.claims} />;
  }

  return (
    <AppShell fullHeight context={project.data?.title} actions={<TopBarActions projectId={projectId} claims={claims.data?.claims} />}>
      {body}
    </AppShell>
  );
}

function TopBarActions({ projectId, claims }: { projectId: string; claims: Claim[] | undefined }) {
  if (!claims || claims.length === 0) return null;
  const reviewed = claims.filter((c) => c.review_status === "REVIEWED").length;
  const complete = reviewed === claims.length;
  return (
    <>
      <span className="hidden text-sm text-ink-2 tabular-nums sm:inline">
        {reviewed} of {claims.length} reviewed
      </span>
      {complete && (
        <Link
          to={`/review/${projectId}/complete`}
          className="hidden h-8 items-center gap-1.5 rounded-md px-2.5 text-sm font-medium text-accent hover:bg-accent-soft sm:inline-flex"
        >
          <ListChecks className="size-3.5" aria-hidden /> Summary
        </Link>
      )}
      <ExportMenu projectId={projectId} />
    </>
  );
}

interface WorkspaceProps {
  projectId: string;
  draftId: string;
  claims: Claim[];
}

function Workspace({ projectId, draftId, claims }: WorkspaceProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const { saves, save, clearError } = useClaimSaves(draftId, projectId);
  const reassess = useReassess(draftId);
  const [filter, setFilter] = useState<ClaimFilter>("all");
  const [edits, setEdits] = useState<Record<string, ReviewFormValues>>({});
  const [panel, setPanel] = useState<"review" | "evidence">("review");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [failedElsewhere, setFailedElsewhere] = useState<string | null>(null);
  const pendingSaves = useRef(new Map<string, Promise<unknown>>());
  const bypassBlock = useRef(false);

  const requested = params.get("claim");
  const selected =
    claims.find((c) => c.id === requested) ?? claims.find((c) => c.review_status === "NEEDS_REVIEW") ?? claims[0]!;
  const position = claims.indexOf(selected) + 1;
  const values = edits[selected.id] ?? savedValues(selected);
  const selectedDirty = saves[selected.id]?.status !== "saving" && isDirty(values, selected);
  const anyDirty =
    selectedDirty ||
    claims.some((c) => edits[c.id] && saves[c.id]?.status !== "saving" && isDirty(edits[c.id]!, c));
  const dirtyRef = useRef(selectedDirty);
  dirtyRef.current = selectedDirty;
  // Latest values for async callbacks (a save can fail before the next render).
  const latest = useRef({ selectedId: selected.id, edits, claims });
  latest.current = { selectedId: selected.id, edits, claims };
  const hasUnsavedEdits = (claimId: string) => {
    const { edits: e, claims: list } = latest.current;
    const claim = list.find((c) => c.id === claimId);
    return Boolean(claim && e[claimId] && isDirty(e[claimId], claim));
  };
  const savingIds = useMemo(
    () => new Set(Object.entries(saves).filter(([, s]) => s.status === "saving").map(([id]) => id)),
    [saves],
  );
  const next = nextUnreviewed(claims, selected.id, savingIds);

  // Keep the URL pointing at the claim actually shown (deep links, reloads).
  useEffect(() => {
    if (requested !== selected.id) {
      bypassBlock.current = true;
      setParams({ claim: selected.id }, { replace: true });
    }
  }, [requested, selected.id, setParams]);

  // One guard for claim switches, links and the browser back button.
  const blocker = useBlocker(({ currentLocation, nextLocation }) => {
    if (bypassBlock.current) {
      bypassBlock.current = false;
      return false;
    }
    const moving =
      currentLocation.pathname !== nextLocation.pathname || currentLocation.search !== nextLocation.search;
    return moving && dirtyRef.current;
  });
  const leavingId = useRef<string | null>(null);
  if (blocker.state === "blocked" && leavingId.current === null) leavingId.current = selected.id;

  useEffect(() => {
    if (!anyDirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [anyDirty]);

  const go = useCallback(
    (claimId: string, { force = false } = {}) => {
      if (force) bypassBlock.current = true;
      setParams({ claim: claimId });
      setDrawerOpen(false);
      setPanel("review");
    },
    [setParams],
  );

  const setValues = (v: ReviewFormValues) => setEdits((e) => ({ ...e, [selected.id]: v }));
  const dropEdits = (claimId: string, ifSame?: ReviewFormValues) =>
    setEdits(({ [claimId]: current, ...rest }) => (ifSame && current !== ifSame ? { ...rest, [claimId]: current! } : rest));

  const runSave = (claim: Claim, submitted: ReviewFormValues) => {
    const promise = save(claim.id, toReviewInput(submitted));
    pendingSaves.current.set(claim.id, promise);
    void promise
      .then(() => dropEdits(claim.id, submitted))
      .catch(() => undefined)
      .finally(() => pendingSaves.current.delete(claim.id));
    return promise;
  };

  const finishIfComplete = async () => {
    await Promise.allSettled(pendingSaves.current.values());
    const latest = queryClient.getQueryData<DraftClaims>(queryKeys.draftClaims(draftId))?.claims ?? [];
    const remaining = latest.find((c) => c.review_status === "NEEDS_REVIEW");
    if (!remaining) navigate(`/review/${projectId}/complete`);
    else go(remaining.id, { force: true });
  };

  const handleSave = async () => {
    if (validationError(values)) return;
    clearError(selected.id);
    try {
      await runSave(selected, values);
    } catch {
      // Error is shown in the save bar; the form keeps the reviewer's input.
    }
  };

  const handleSaveNext = async () => {
    const claim = selected;
    const submitted = values;
    const unchanged = !isDirty(submitted, claim) && claim.review;
    if (unchanged) {
      if (next) go(next.id);
      return;
    }
    if (validationError(submitted)) return;
    clearError(claim.id);
    setEdits((e) => ({ ...e, [claim.id]: submitted })); // kept until the server confirms

    if (!next) {
      // Last claim: wait for the save, then show the completion summary.
      try {
        await runSave(claim, submitted);
        await finishIfComplete();
      } catch {
        // Stay on the claim; the error is shown and the input kept.
      }
      return;
    }

    // Optimistic: move on now, mark the claim "Saving…", and come back with the
    // reviewer's input intact if the save fails.
    latest.current.selectedId = next.id;
    go(next.id, { force: true });
    try {
      await runSave(claim, submitted);
    } catch {
      const current = latest.current.selectedId;
      // Don't yank the reviewer away from unsaved work on another claim.
      if (current !== claim.id && hasUnsavedEdits(current)) setFailedElsewhere(claim.id);
      else go(claim.id, { force: true });
    }
  };

  const reassessThis = reassess.variables === selected.id;

  return (
    <div className="flex h-full min-h-0">
      <aside className="hidden w-[280px] shrink-0 border-r border-line bg-canvas md:flex md:flex-col">
        <ClaimSidebar
          claims={claims}
          selectedId={selected.id}
          filter={filter}
          onFilterChange={setFilter}
          onSelect={(id) => id !== selected.id && go(id)}
          saves={saves}
        />
      </aside>

      {drawerOpen && (
        <div className="fixed inset-0 z-40 md:hidden" role="dialog" aria-modal="true" aria-label="Claims">
          <button type="button" aria-label="Close claims" className="absolute inset-0 bg-ink/30" onClick={() => setDrawerOpen(false)} />
          <div className="absolute inset-y-0 left-0 flex w-[min(320px,85vw)] flex-col bg-canvas shadow-xl">
            <div className="flex justify-end p-2">
              <Button size="sm" variant="ghost" onClick={() => setDrawerOpen(false)} icon={<X className="size-4" aria-hidden />}>
                Close
              </Button>
            </div>
            <ClaimSidebar
              claims={claims}
              selectedId={selected.id}
              filter={filter}
              onFilterChange={setFilter}
              onSelect={(id) => (id !== selected.id ? go(id) : setDrawerOpen(false))}
              saves={saves}
            />
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {failedElsewhere && saves[failedElsewhere]?.status === "error" && (
          <div role="alert" className="flex items-center gap-3 border-b border-unsupported-line bg-danger-soft px-5 py-2.5 text-sm">
            <CircleAlert className="size-4 shrink-0 text-danger" aria-hidden />
            <span className="flex-1 text-ink">
              Claim {claims.findIndex((c) => c.id === failedElsewhere) + 1} wasn't saved. Your decision and note are kept.
            </span>
            <Button size="sm" variant="secondary" onClick={() => { const id = failedElsewhere; setFailedElsewhere(null); go(id); }}>
              Review and retry
            </Button>
          </div>
        )}
        {claims.every((c) => c.review_status === "REVIEWED") && (
          <div className="flex items-center gap-2.5 border-b border-line bg-accent-soft/50 px-5 py-2 text-sm">
            <CircleCheck className="size-4 text-accent" aria-hidden />
            <span className="flex-1 text-ink">All claims reviewed. Decisions remain editable.</span>
            <Link to={`/review/${projectId}/complete`} className="font-medium text-accent underline-offset-4 hover:underline">
              View summary
            </Link>
          </div>
        )}

        <div className="flex h-11 shrink-0 items-center gap-1 border-b border-line bg-surface px-3 xl:hidden" role="tablist" aria-label="Workspace view">
          <Button size="sm" variant="ghost" className="md:hidden" onClick={() => setDrawerOpen(true)} icon={<ListChecks className="size-4" aria-hidden />}>
            Claims
          </Button>
          {(["review", "evidence"] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              role="tab"
              aria-selected={panel === tab}
              onClick={() => setPanel(tab)}
              className={`h-8 rounded-[5px] px-3 text-sm font-medium ${panel === tab ? "bg-subtle text-ink" : "text-ink-2 hover:text-ink"}`}
            >
              {tab === "review" ? "Review" : `Evidence (${selected.evidence.length})`}
            </button>
          ))}
        </div>

        <div className="flex min-h-0 flex-1">
          <div className={`${panel === "evidence" ? "hidden xl:flex" : "flex"} min-w-0 flex-1 flex-col bg-surface`}>
            <ClaimReview
              key={selected.id}
              claim={selected}
              position={position}
              total={claims.length}
              values={values}
              onChange={setValues}
              saveState={saves[selected.id]}
              onSave={handleSave}
              onSaveNext={handleSaveNext}
              hasNext={Boolean(next)}
              reassessing={reassessThis && reassess.isPending}
              reassessError={reassessThis && reassess.isError ? toUserError(reassess.error) : null}
              onReassess={() => reassess.mutate(selected.id)}
            />
          </div>
          <aside
            aria-label="Evidence"
            className={`${panel === "evidence" ? "flex" : "hidden xl:flex"} w-full min-w-0 shrink-0 flex-col border-l border-line bg-evidence xl:w-[400px] 2xl:w-[440px]`}
          >
            <EvidencePanel claim={selected} />
          </aside>
        </div>
      </div>

      <ConfirmDialog
        open={blocker.state === "blocked"}
        title="Discard unsaved changes?"
        description={`Your decision or note for claim ${claims.findIndex((c) => c.id === leavingId.current) + 1} hasn't been saved.`}
        confirmLabel="Discard changes"
        onConfirm={() => {
          if (leavingId.current) dropEdits(leavingId.current);
          leavingId.current = null;
          blocker.proceed?.();
        }}
        onCancel={() => {
          leavingId.current = null;
          blocker.reset?.();
        }}
      />
    </div>
  );
}

function ReanalyzePrompt({ draftId, projectId }: { draftId: string; projectId: string }) {
  const queryClient = useQueryClient();
  const analyze = useMutation({
    mutationFn: () => analyzeDraft(draftId),
    onSuccess: (result) => {
      queryClient.setQueryData<DraftClaims>(queryKeys.draftClaims(draftId), {
        draft_id: result.draft_id,
        project_id: result.project_id,
        claims: result.claims,
      });
      void queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) });
    },
  });
  return (
    <CenteredMessage title="This draft hasn't been analyzed" text="The previous analysis didn't complete. Run it again to extract and assess the claims.">
      {analyze.isError && <InlineError title="Analysis didn't complete" error={toUserError(analyze.error)} />}
      <Button variant="primary" loading={analyze.isPending} onClick={() => analyze.mutate()}>
        {analyze.isPending ? "Analyzing…" : "Analyze draft"}
      </Button>
    </CenteredMessage>
  );
}

function CenteredMessage({ title, text, icon, children }: { title: string; text: string; icon?: ReactNode; children?: ReactNode }) {
  return (
    <div className="mx-auto flex max-w-md flex-col items-start gap-3 px-6 py-24">
      {icon}
      <h1 className="text-xl font-semibold">{title}</h1>
      <p className="text-ink-2">{text}</p>
      {children && <div className="mt-2 flex w-full flex-col items-start gap-3">{children}</div>}
    </div>
  );
}

function CenteredError({ title, error, onRetry }: { title: string; error: unknown; onRetry: () => void }) {
  return (
    <div className="mx-auto max-w-lg px-6 py-24">
      <InlineError
        title={title}
        error={toUserError(error)}
        action={
          <Button size="sm" variant="secondary" onClick={onRetry}>
            Try again
          </Button>
        }
      />
    </div>
  );
}

function WorkspaceSkeleton() {
  const bar = "rounded bg-line/70 animate-pulse";
  return (
    <div className="flex h-full" aria-busy="true" aria-label="Loading review">
      <div className="hidden w-[280px] shrink-0 space-y-4 border-r border-line bg-canvas p-4 md:block">
        {[0, 1, 2].map((i) => (
          <div key={i} className="space-y-2">
            <div className={`${bar} h-3.5 w-full`} />
            <div className={`${bar} h-3.5 w-2/3`} />
          </div>
        ))}
      </div>
      <div className="flex-1 space-y-4 bg-surface px-8 py-8">
        <div className={`${bar} h-3 w-24`} />
        <div className={`${bar} h-6 w-4/5`} />
        <div className={`${bar} h-6 w-3/5`} />
        <div className={`${bar} mt-6 h-28 w-full`} />
      </div>
      <div className="hidden w-[400px] shrink-0 space-y-3 border-l border-line bg-canvas p-5 xl:block">
        <div className={`${bar} h-4 w-4/5`} />
        <div className={`${bar} h-3 w-1/2`} />
        <div className={`${bar} mt-6 h-24 w-full`} />
      </div>
    </div>
  );
}

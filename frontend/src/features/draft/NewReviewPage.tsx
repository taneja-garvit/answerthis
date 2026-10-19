import { FileText, RotateCcw } from "lucide-react";
import { useId, useRef, useState } from "react";
import { useNavigate } from "react-router";

import { AppShell } from "../../components/AppShell";
import { Button } from "../../components/Button";
import { InlineError } from "../../components/InlineError";
import { toUserError } from "../../lib/errors";
import { EXAMPLE_DRAFT, MAX_DRAFT_CHARS } from "../../lib/exampleDraft";
import { AnalysisLoading } from "./AnalysisLoading";
import { useStartReview } from "./useStartReview";

export function NewReviewPage() {
  const [text, setText] = useState("");
  const editorRef = useRef<HTMLTextAreaElement>(null);
  const navigate = useNavigate();
  const startReview = useStartReview();
  const hintId = useId();

  const trimmed = text.trim();
  const tooLong = trimmed.length > MAX_DRAFT_CHARS;
  const analyzing = startReview.isPending;
  const canSubmit = trimmed.length > 0 && !tooLong && !analyzing;

  const submit = () => {
    if (!canSubmit) return;
    startReview.mutate(trimmed, {
      onSuccess: ({ project }) => navigate(`/review/${project.id}`),
    });
  };

  const loadExample = () => {
    setText(EXAMPLE_DRAFT);
    startReview.reset();
    editorRef.current?.focus();
  };

  return (
    <AppShell>
      <div className="mx-auto max-w-3xl px-5 pt-10 pb-16 sm:px-6 sm:pt-[9vh]">
        <h1 className="text-xl font-semibold tracking-[-0.01em]">Review a research draft</h1>
        <p className="mt-1 max-w-2xl text-md text-ink-2">
          Analyze the claims in your draft against their cited evidence, then review each finding
          yourself.
        </p>

        <form
          className="mt-6"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          <label htmlFor="draft" className="sr-only">
            Research draft
          </label>
          <div
            className={`rounded-lg border bg-surface shadow-[0_1px_2px_rgba(30,28,25,0.04)] transition-colors focus-within:border-ink-3/50 ${
              tooLong ? "border-unsupported-line" : "border-line-strong/80"
            } ${analyzing ? "opacity-70" : ""}`}
          >
            <textarea
              id="draft"
              ref={editorRef}
              value={text}
              onChange={(event) => setText(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) submit();
              }}
              readOnly={analyzing}
              aria-describedby={hintId}
              aria-invalid={tooLong || undefined}
              placeholder="Paste a research paragraph or draft with citations…"
              spellCheck
              className="block min-h-80 w-full resize-y rounded-lg bg-transparent px-5 py-4 text-md leading-7 text-ink placeholder:text-ink-3 focus:outline-none"
            />
            <div
              id={hintId}
              className="flex items-center justify-between gap-4 rounded-b-lg border-t border-line bg-tint px-5 py-2 text-sm text-ink-3"
            >
              <span>Supports numbered citations such as [1] or [1–3], and DOI references.</span>
              <span className={`tabular-nums ${tooLong ? "font-medium text-danger" : ""}`}>
                {trimmed.length.toLocaleString()} / {MAX_DRAFT_CHARS.toLocaleString()}
              </span>
            </div>
          </div>
          {tooLong && (
            <p className="mt-2 text-sm text-danger">
              The draft is longer than the 20,000-character limit. Shorten it to analyze.
            </p>
          )}

          <div className="mt-4 flex items-center justify-between gap-2">
            <Button
              variant="ghost"
              icon={<FileText className="size-4" aria-hidden />}
              onClick={loadExample}
              disabled={analyzing}
              className="-ml-2"
            >
              Load example
            </Button>
            <Button type="submit" variant="primary" disabled={!canSubmit} loading={analyzing}>
              {analyzing ? "Analyzing…" : "Analyze draft"}
            </Button>
          </div>
        </form>

        <div className="mt-6">
          {analyzing && <AnalysisLoading />}
          {startReview.isError && (
            <InlineError
              title="Analysis didn't complete"
              error={toUserError(startReview.error)}
              action={
                <>
                  <Button
                    variant="primary"
                    size="sm"
                    icon={<RotateCcw className="size-3.5" aria-hidden />}
                    onClick={submit}
                    disabled={!canSubmit}
                  >
                    Retry analysis
                  </Button>
                  <Button variant="secondary" size="sm" onClick={() => editorRef.current?.focus()}>
                    Edit draft
                  </Button>
                </>
              }
            />
          )}
        </div>

        {!analyzing && !startReview.isError && (
          <p className="mt-8 max-w-2xl text-sm leading-6 text-ink-3">
            The AI suggests an assessment for each claim from the evidence it can access. You make
            every decision, and nothing changes in your draft without you.
          </p>
        )}
      </div>
    </AppShell>
  );
}

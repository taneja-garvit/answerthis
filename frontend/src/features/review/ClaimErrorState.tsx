import { CircleAlert, RotateCcw } from "lucide-react";

import { Button } from "../../components/Button";

export function ClaimErrorState({ message, onRetry, retrying }: { message: string | null; onRetry: () => void; retrying: boolean }) {
  return (
    <section role="status" className="rounded-lg border border-unsupported-line bg-danger-soft px-4 py-4">
      <div className="flex gap-3">
        <CircleAlert className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden />
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold text-ink">Assessment couldn't be completed</h3>
          <p className="mt-1 text-ink-2">
            {message ?? "The AI assessment for this claim did not finish."} You can still review the
            claim yourself, or retry the assessment.
          </p>
          <div className="mt-3">
            <Button
              size="sm"
              variant="secondary"
              onClick={onRetry}
              loading={retrying}
              icon={<RotateCcw className="size-3.5" aria-hidden />}
            >
              {retrying ? "Retrying…" : "Retry assessment"}
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}

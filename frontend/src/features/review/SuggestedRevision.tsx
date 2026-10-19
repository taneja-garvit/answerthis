import { CornerDownRight } from "lucide-react";

import { Button } from "../../components/Button";

/** Visibly a suggestion: dashed, secondary, never applied or saved automatically. */
export function SuggestedRevision({ text, onUse, disabled }: { text: string; onUse: () => void; disabled: boolean }) {
  return (
    <section aria-labelledby="suggested-revision" className="rounded-lg border border-dashed border-line-strong px-4 py-3.5">
      <div className="flex items-center justify-between gap-3">
        <h3 id="suggested-revision" className="section-label">
          AI suggested revision
        </h3>
        <Button
          size="sm"
          variant="secondary"
          onClick={onUse}
          disabled={disabled}
          icon={<CornerDownRight className="size-3.5" aria-hidden />}
        >
          Use suggestion
        </Button>
      </div>
      <p className="text-wrap-anywhere mt-2 text-md leading-7 text-ink">{text}</p>
      <p className="mt-1.5 text-sm text-ink-3">Not verified. Check it against the evidence and edit before saving.</p>
    </section>
  );
}

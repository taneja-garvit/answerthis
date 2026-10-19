import type { Evidence } from "../../api/types";
import { ACCESS_COPY } from "../../lib/labels";
import { segment, sharedNumberRanges } from "../../lib/highlight";

interface EvidencePassageProps {
  evidence: Evidence;
  /** Text whose numbers are highlighted in the passage (claim + issue values). */
  reference: string;
  emphasis: "primary" | "secondary";
}

export function EvidencePassage({ evidence, reference, emphasis }: EvidencePassageProps) {
  const parts = segment(evidence.passage, sharedNumberRanges(evidence.passage, reference));
  const primary = emphasis === "primary";
  return (
    <figure
      className={
        primary
          ? "rounded-md border border-line bg-surface px-4 py-3.5"
          : "border-l-2 border-line pl-3.5"
      }
    >
      <blockquote className={`text-wrap-anywhere ${primary ? "text-md leading-7 text-ink" : "text-base leading-6 text-ink-2"}`}>
        {parts.map((part, i) =>
          part.marked ? <mark key={i}>{part.text}</mark> : <span key={i}>{part.text}</span>,
        )}
      </blockquote>
      <figcaption className="mt-1.5 flex flex-wrap gap-x-2 text-xs text-ink-3">
        {evidence.location && <span>{evidence.location}</span>}
        <span aria-hidden>·</span>
        <span>{ACCESS_COPY[evidence.access_level].label}</span>
        {evidence.is_synthetic && <span className="font-medium text-partial">· Synthetic text, not from the source</span>}
      </figcaption>
    </figure>
  );
}

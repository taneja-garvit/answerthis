import { ChevronRight, FileSearch, FileText } from "lucide-react";

import type { Claim } from "../../api/types";
import { ACCESS_COPY } from "../../lib/labels";
import { EvidencePassage } from "./EvidencePassage";
import { SourceMetadata } from "./SourceMetadata";

export function EvidencePanel({ claim }: { claim: Claim }) {
  const { evidence, evidence_availability: availability, assessment } = claim;
  const usedIds = new Set(assessment?.evidence_ids ?? []);
  const used = evidence.filter((e) => usedIds.has(e.id));
  const additional = evidence.filter((e) => !usedIds.has(e.id));
  const reference = [
    claim.claim_text,
    ...(assessment?.issues ?? []).flatMap((i) => [i.claim_value ?? "", i.evidence_value ?? ""]),
  ].join(" ");
  const unavailable = availability.status === "UNAVAILABLE";

  return (
    <section aria-labelledby="evidence-heading" className="flex h-full min-h-0 flex-col">
      <div className="flex h-12 shrink-0 items-center border-b border-line bg-evidence px-5">
        <h2 id="evidence-heading" className="text-md font-semibold">
          Evidence
        </h2>
      </div>
      <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-5 pt-5 pb-10">
        {claim.sources.length > 0 ? (
          <div className="space-y-5">
            {claim.sources.map((source) => (
              <SourceMetadata key={source.id} source={source} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-ink-2">No cited source is linked to this claim.</p>
        )}

        {!unavailable && (
          <p className="mt-4 flex items-center gap-2 text-sm text-ink-2">
            <FileText className="size-3.5 text-ink-3" aria-hidden />
            {ACCESS_COPY[availability.status].note}
          </p>
        )}

        <div className="mt-6 border-t border-line pt-5">
          {unavailable ? (
            <div className="rounded-md border border-dashed border-line-strong px-4 py-5 text-center">
              <FileSearch className="mx-auto size-5 text-ink-3" aria-hidden />
              <h3 className="mt-2 font-semibold text-ink">Evidence unavailable</h3>
              <p className="mt-1 text-sm leading-5 text-ink-2">{availability.message}</p>
              <p className="mt-2 text-sm leading-5 text-ink-3">
                No passage is shown because none could be accessed; nothing is filled in for it.
              </p>
            </div>
          ) : used.length > 0 ? (
            <>
              <h3 className="section-label">Used in assessment</h3>
              <ul className="mt-3 space-y-5">
                {used.map((e) => (
                  <li key={e.id}>
                    <EvidencePassage evidence={e} reference={reference} emphasis="primary" />
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <>
              <h3 className="section-label">Retrieved passages</h3>
              <p className="mt-1.5 text-xs text-ink-3">Retrieved by relevance; not necessarily supporting.</p>
              <ul className="mt-3 space-y-4">
                {additional.map((e) => (
                  <li key={e.id}>
                    <EvidencePassage evidence={e} reference={reference} emphasis="secondary" />
                  </li>
                ))}
              </ul>
            </>
          )}

          {used.length > 0 && additional.length > 0 && (
            <details className="group mt-6">
              <summary className="flex cursor-pointer list-none items-center gap-1.5 rounded-sm text-sm font-medium text-ink-2 hover:text-ink [&::-webkit-details-marker]:hidden">
                <ChevronRight className="size-4 transition-transform group-open:rotate-90" aria-hidden />
                Additional retrieved passages ({additional.length})
              </summary>
              <p className="mt-1.5 ml-5.5 text-xs text-ink-3">Retrieved by relevance; not necessarily supporting.</p>
              <ul className="mt-3 space-y-4">
                {additional.map((e) => (
                  <li key={e.id}>
                    <EvidencePassage evidence={e} reference={reference} emphasis="secondary" />
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      </div>
    </section>
  );
}

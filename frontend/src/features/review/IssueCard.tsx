import { TriangleAlert } from "lucide-react";

import type { Issue } from "../../api/types";
import { ISSUE_LABELS } from "../../lib/labels";

export function IssueCard({ issue }: { issue: Issue }) {
  const hasValues = Boolean(issue.claim_value || issue.evidence_value);
  return (
    <li className="rounded-md border border-line border-l-partial-line bg-surface [border-left-width:3px]">
      <div className="flex items-center gap-2 px-4 pt-3">
        <TriangleAlert className="size-4 text-partial" aria-hidden />
        <h4 className="font-semibold text-ink">{ISSUE_LABELS[issue.type]}</h4>
      </div>
      {hasValues && (
        <dl className="mx-4 mt-2.5 grid gap-px overflow-hidden rounded-[5px] border border-line bg-line sm:grid-cols-2">
          {issue.claim_value && (
            <div className="bg-tint px-3 py-2">
              <dt className="text-xs font-medium text-ink-3">Claim</dt>
              <dd className="text-wrap-anywhere mt-0.5 text-md font-semibold text-ink">{issue.claim_value}</dd>
            </div>
          )}
          {issue.evidence_value && (
            <div className="bg-tint px-3 py-2">
              <dt className="text-xs font-medium text-ink-3">Evidence</dt>
              <dd className="text-wrap-anywhere mt-0.5 text-md font-semibold text-ink">{issue.evidence_value}</dd>
            </div>
          )}
        </dl>
      )}
      <p className="text-wrap-anywhere px-4 pt-2.5 pb-3.5 text-base leading-6 text-ink-2">{issue.description}</p>
    </li>
  );
}

import { CircleAlert, CircleCheck } from "lucide-react";

import type { Claim } from "../../api/types";
import { Spinner } from "../../components/Spinner";
import { VerdictBadge } from "../../components/VerdictBadge";
import { DECISIONS } from "../../lib/labels";
import { pad2 } from "../../lib/format";
import type { SaveState } from "./useClaimSaves";

interface ClaimListItemProps {
  claim: Claim;
  selected: boolean;
  saveState: SaveState | undefined;
  onSelect: () => void;
}

function ReviewState({ claim, saveState }: { claim: Claim; saveState: SaveState | undefined }) {
  if (saveState?.status === "saving") {
    return (
      <span className="inline-flex items-center gap-1 text-ink-2">
        <Spinner className="size-3" /> Saving…
      </span>
    );
  }
  if (saveState?.status === "error") {
    return (
      <span className="inline-flex items-center gap-1 font-medium text-danger">
        <CircleAlert className="size-3.5" aria-hidden /> Save failed
      </span>
    );
  }
  if (claim.review) {
    return (
      <span className="inline-flex items-center gap-1 text-ink-2">
        <CircleCheck className="size-3.5 text-accent" aria-hidden />
        Reviewed · {DECISIONS[claim.review.decision].label}
      </span>
    );
  }
  return <span className="text-ink-3">Needs review</span>;
}

export function ClaimListItem({ claim, selected, saveState, onSelect }: ClaimListItemProps) {
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        aria-current={selected ? "true" : undefined}
        className={`group relative flex w-full gap-3 border-l-2 px-4 py-3 text-left transition-colors ${
          selected ? "border-accent bg-accent-soft/60" : "border-transparent hover:bg-subtle"
        }`}
      >
        <span
          className={`pt-px text-sm font-semibold tabular-nums ${selected ? "text-accent" : "text-ink-3"}`}
        >
          {pad2(claim.order)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="text-wrap-anywhere line-clamp-2 text-base leading-snug text-ink">{claim.claim_text}</span>
          <span className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
            {claim.assessment ? (
              <VerdictBadge verdict={claim.assessment.verdict} size="sm" />
            ) : claim.status === "ERROR" ? (
              <span className="font-medium text-danger">Assessment failed</span>
            ) : (
              <span className="text-ink-3">Not assessed</span>
            )}
            <ReviewState claim={claim} saveState={saveState} />
          </span>
        </span>
      </button>
    </li>
  );
}

import type { Claim } from "../../api/types";
import { ProgressBar } from "../../components/ProgressBar";
import { ClaimListItem } from "./ClaimListItem";
import { FILTERS, matchesFilter, type ClaimFilter } from "./filters";
import type { SaveState } from "./useClaimSaves";

interface ClaimSidebarProps {
  claims: Claim[];
  selectedId: string | undefined;
  filter: ClaimFilter;
  onFilterChange: (filter: ClaimFilter) => void;
  onSelect: (claimId: string) => void;
  saves: Record<string, SaveState>;
}

export function ClaimSidebar({ claims, selectedId, filter, onFilterChange, onSelect, saves }: ClaimSidebarProps) {
  const reviewed = claims.filter((c) => c.review_status === "REVIEWED").length;
  const visible = claims.filter((c) => matchesFilter(c, filter));

  return (
    <nav aria-label="Claims" className="flex h-full min-h-0 flex-col">
      <div className="border-b border-line px-4 pt-4 pb-3">
        <div className="flex items-baseline justify-between">
          <h2 className="text-md font-semibold">Claims</h2>
          <span className="text-sm text-ink-2 tabular-nums">
            {reviewed} of {claims.length} reviewed
          </span>
        </div>
        <div className="mt-2.5">
          <ProgressBar value={reviewed} total={claims.length} label="Review progress" />
        </div>
        <div role="group" aria-label="Filter claims" className="mt-3 flex flex-wrap gap-1">
          {FILTERS.map((option) => {
            const count = claims.filter((c) => matchesFilter(c, option.id)).length;
            const active = option.id === filter;
            return (
              <button
                key={option.id}
                type="button"
                aria-pressed={active}
                onClick={() => onFilterChange(option.id)}
                className={`h-7 rounded-[5px] border px-2 text-xs font-medium transition-colors ${
                  active
                    ? "border-ink/80 bg-ink text-white"
                    : "border-line bg-surface text-ink-2 hover:border-line-strong hover:text-ink"
                }`}
              >
                {option.label}
                <span className={`ml-1 tabular-nums ${active ? "text-white/70" : "text-ink-3"}`}>{count}</span>
              </button>
            );
          })}
        </div>
      </div>
      {visible.length === 0 ? (
        <p className="px-4 py-6 text-sm text-ink-3">No claims match this filter.</p>
      ) : (
        <ol className="min-h-0 flex-1 divide-y divide-line overflow-y-auto py-1">
          {visible.map((claim) => (
            <ClaimListItem
              key={claim.id}
              claim={claim}
              selected={claim.id === selectedId}
              saveState={saves[claim.id]}
              onSelect={() => onSelect(claim.id)}
            />
          ))}
        </ol>
      )}
    </nav>
  );
}

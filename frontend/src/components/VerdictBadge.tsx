import type { Verdict } from "../api/types";
import { VERDICTS } from "../lib/labels";

/** AI verdict chip: semantic tone + icon + text, never colour alone. */
export function VerdictBadge({ verdict, size = "md" }: { verdict: Verdict; size?: "sm" | "md" }) {
  const meta = VERDICTS[verdict];
  const Icon = meta.icon;
  const sizing = size === "sm" ? "h-5 px-1.5 text-xs gap-1" : "h-7 px-2.5 text-sm gap-1.5";
  return (
    <span className={`inline-flex items-center rounded-[4px] border font-medium ${meta.tone} ${sizing}`}>
      <Icon className={size === "sm" ? "size-3" : "size-3.5"} aria-hidden strokeWidth={2.25} />
      {size === "sm" ? meta.short : meta.label}
    </span>
  );
}

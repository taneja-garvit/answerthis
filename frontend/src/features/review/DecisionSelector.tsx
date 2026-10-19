import { useRef } from "react";

import type { ReviewDecision } from "../../api/types";
import { DECISION_ORDER, DECISIONS } from "../../lib/labels";

interface DecisionSelectorProps {
  value: ReviewDecision | null;
  onChange: (decision: ReviewDecision) => void;
  disabled: boolean;
  describedBy: string;
}

/** Radio group (roving tabindex, arrow keys). Selection uses the wine accent:
 *  it is the researcher's own judgement. */
export function DecisionSelector({ value, onChange, disabled, describedBy }: DecisionSelectorProps) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const focusIndex = value ? DECISION_ORDER.indexOf(value) : 0;

  const move = (from: number, delta: number) => {
    const next = (from + delta + DECISION_ORDER.length) % DECISION_ORDER.length;
    onChange(DECISION_ORDER[next]!);
    refs.current[next]?.focus();
  };

  return (
    <div role="radiogroup" aria-label="Your decision" aria-describedby={describedBy} className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {DECISION_ORDER.map((decision, index) => {
        const meta = DECISIONS[decision];
        const Icon = meta.icon;
        const checked = value === decision;
        return (
          <button
            key={decision}
            ref={(el) => {
              refs.current[index] = el;
            }}
            type="button"
            role="radio"
            aria-checked={checked}
            tabIndex={index === focusIndex ? 0 : -1}
            disabled={disabled}
            onClick={() => onChange(decision)}
            onKeyDown={(event) => {
              if (event.key === "ArrowRight" || event.key === "ArrowDown") {
                event.preventDefault();
                move(index, 1);
              } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
                event.preventDefault();
                move(index, -1);
              }
            }}
            className={`flex h-10 items-center justify-center gap-2 rounded-md border text-base font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
              checked
                ? "border-accent bg-accent text-white shadow-[inset_0_0_0_1px_rgba(255,255,255,0.12)]"
                : "border-line bg-surface text-ink-2 hover:border-accent-line hover:bg-accent-soft/40 hover:text-ink"
            }`}
          >
            <Icon className="size-4" aria-hidden strokeWidth={2.25} />
            {meta.label}
          </button>
        );
      })}
    </div>
  );
}

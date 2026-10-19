import {
  ArrowLeftRight,
  Check,
  CircleAlert,
  CircleCheck,
  CircleHelp,
  CircleX,
  PenLine,
  Trash2,
  type LucideIcon,
} from "lucide-react";

import type { ConfidenceLevel, EvidenceAvailability, IssueType, ReviewDecision, Verdict } from "../api/types";

export interface VerdictMeta {
  label: string;
  short: string;
  icon: LucideIcon;
  /** Tailwind classes: text, tinted background, border. */
  tone: string;
}

export const VERDICTS: Record<Verdict, VerdictMeta> = {
  SUPPORTED: {
    label: "Supported",
    short: "Supported",
    icon: CircleCheck,
    tone: "text-supported bg-supported-soft border-supported-line",
  },
  PARTIALLY_SUPPORTED: {
    label: "Partially supported",
    short: "Partial",
    icon: CircleAlert,
    tone: "text-partial bg-partial-soft border-partial-line",
  },
  UNSUPPORTED: {
    label: "Unsupported",
    short: "Unsupported",
    icon: CircleX,
    tone: "text-unsupported bg-unsupported-soft border-unsupported-line",
  },
  UNVERIFIABLE: {
    label: "Unverifiable",
    short: "Unverifiable",
    icon: CircleHelp,
    tone: "text-unverifiable bg-unverifiable-soft border-unverifiable-line",
  },
};

export const VERDICT_ORDER: Verdict[] = ["SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "UNVERIFIABLE"];

export const CONFIDENCE_LABELS: Record<ConfidenceLevel, string> = {
  HIGH: "High confidence",
  MEDIUM: "Medium confidence",
  LOW: "Low confidence",
};

export const ISSUE_LABELS: Record<IssueType, string> = {
  FIGURE_MISMATCH: "Figure mismatch",
  POPULATION_MISMATCH: "Population mismatch",
  OUTCOME_MISMATCH: "Outcome mismatch",
  OVERGENERALIZATION: "Overgeneralization",
  CAUSAL_OVERSTATEMENT: "Causal overstatement",
  WORDING_STRENGTH: "Wording stronger than evidence",
  SOURCE_MISMATCH: "Source mismatch",
  INSUFFICIENT_EVIDENCE: "Insufficient evidence",
  EVIDENCE_UNAVAILABLE: "Evidence unavailable",
  OTHER: "Other",
};

export interface DecisionMeta {
  label: string;
  icon: LucideIcon;
  help: string;
}

export const DECISIONS: Record<ReviewDecision, DecisionMeta> = {
  KEEP: { label: "Keep", icon: Check, help: "The claim can remain as written." },
  QUALIFY: {
    label: "Qualify",
    icon: PenLine,
    help: "The claim is useful, but its wording should be narrowed or corrected.",
  },
  REPLACE: {
    label: "Replace",
    icon: ArrowLeftRight,
    help: "Replace the claim with different wording or evidence.",
  },
  REMOVE: { label: "Remove", icon: Trash2, help: "The claim should not remain in the draft." },
};

export const DECISION_ORDER: ReviewDecision[] = ["KEEP", "QUALIFY", "REPLACE", "REMOVE"];

export const ACCESS_COPY: Record<EvidenceAvailability, { label: string; note: string }> = {
  ABSTRACT: { label: "Abstract", note: "Assessment based on the public abstract." },
  FULL_TEXT: { label: "Open-access full text", note: "Assessment based on open-access full text." },
  USER_PROVIDED: { label: "User-provided text", note: "Assessment based on text you provided." },
  UNAVAILABLE: { label: "Unavailable", note: "Evidence unavailable." },
};

export const NEEDS_ATTENTION: Verdict[] = ["PARTIALLY_SUPPORTED", "UNSUPPORTED", "UNVERIFIABLE"];

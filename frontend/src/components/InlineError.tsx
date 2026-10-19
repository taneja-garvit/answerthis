import { CircleAlert } from "lucide-react";
import type { ReactNode } from "react";

import type { UserFacingError } from "../lib/errors";

export function InlineError({
  title,
  error,
  action,
}: {
  title: string;
  error: UserFacingError;
  action?: ReactNode;
}) {
  return (
    <div role="alert" className="flex gap-3 rounded-md border border-unsupported-line bg-danger-soft px-4 py-3">
      <CircleAlert className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="font-semibold text-ink">{title}</p>
        <p className="mt-0.5 text-ink-2">{error.message}</p>
        {error.requestId && (
          <p className="mt-1 text-xs text-ink-3">Reference: {error.requestId}</p>
        )}
        {action && <div className="mt-3 flex gap-2">{action}</div>}
      </div>
    </div>
  );
}

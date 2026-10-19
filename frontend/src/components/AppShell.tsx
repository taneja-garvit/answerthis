import type { ReactNode } from "react";
import { Link } from "react-router";

interface AppShellProps {
  /** Context shown after the product name, e.g. the project title. */
  context?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  /** Workspace pages fill the viewport and manage their own scrolling. */
  fullHeight?: boolean;
}

export function AppShell({ context, actions, children, fullHeight = false }: AppShellProps) {
  return (
    <div className={fullHeight ? "flex h-dvh flex-col" : "min-h-dvh"}>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-20 flex h-13 shrink-0 items-center gap-4 border-b border-line bg-surface px-4 sm:px-5">
        <Link to="/" className="flex items-center gap-2.5 rounded-sm">
          <span aria-hidden className="grid size-6 place-items-center rounded-[5px] bg-accent">
            <svg viewBox="0 0 32 32" className="size-4">
              <path d="M9 10h14M9 16h9M9 22h12" stroke="white" strokeWidth="2.6" strokeLinecap="round" />
            </svg>
          </span>
          <span className="font-semibold tracking-[-0.01em] text-ink">Evidence Review</span>
          <span className="hidden rounded-[4px] border border-line px-1.5 py-0.5 text-xs font-medium text-ink-3 sm:inline">
            Research review
          </span>
        </Link>
        {context && (
          <div className="flex min-w-0 items-center gap-2 text-ink-2">
            <span aria-hidden className="text-line-strong">
              /
            </span>
            <span className="truncate">{context}</span>
          </div>
        )}
        <div className="ml-auto flex shrink-0 items-center gap-3">{actions}</div>
      </header>
      <main id="main" className={fullHeight ? "min-h-0 flex-1" : undefined}>
        {children}
      </main>
    </div>
  );
}

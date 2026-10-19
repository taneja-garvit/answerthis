import { Link } from "react-router";

import { AppShell } from "../components/AppShell";

export function NotFoundPage() {
  return (
    <AppShell>
      <div className="mx-auto max-w-xl px-6 py-24">
        <h1 className="text-xl font-semibold">Page not found</h1>
        <p className="mt-2 text-ink-2">This address doesn't match a review.</p>
        <Link to="/" className="mt-6 inline-block font-medium text-accent underline-offset-4 hover:underline">
          Start a new review
        </Link>
      </div>
    </AppShell>
  );
}

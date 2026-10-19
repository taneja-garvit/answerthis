import { ExternalLink } from "lucide-react";

import type { SourceSummary } from "../../api/types";
import { doiUrl, formatAuthors } from "../../lib/format";

export function SourceMetadata({ source }: { source: SourceSummary }) {
  const venue = [source.journal, source.publication_year].filter(Boolean).join(" · ");
  return (
    <div>
      {source.citation_marker && <p className="text-xs font-medium text-ink-3">Cited as {source.citation_marker}</p>}
      <h3 className="text-wrap-anywhere mt-1 text-base leading-snug font-medium text-ink">{source.title}</h3>
      <p className="mt-1.5 text-sm text-ink-3">{formatAuthors(source.authors)}</p>
      {venue && <p className="text-sm text-ink-3">{venue}</p>}
      {source.doi && (
        <a
          href={doiUrl(source.doi)}
          target="_blank"
          rel="noopener noreferrer"
          className="text-wrap-anywhere mt-1.5 inline-flex items-center gap-1 text-sm font-medium text-accent underline underline-offset-4 decoration-accent-line hover:decoration-accent"
        >
          doi:{source.doi}
          <ExternalLink className="size-3.5" aria-hidden />
          <span className="sr-only">(opens in a new tab)</span>
        </a>
      )}
    </div>
  );
}

import type { Author } from "../api/types";

function authorName(author: Author): string | null {
  if (author.family) {
    const initials = (author.given ?? "")
      .split(/[\s.-]+/)
      .filter(Boolean)
      .map((part) => part[0]?.toUpperCase())
      .join("");
    return initials ? `${author.family} ${initials}` : author.family;
  }
  return author.name ?? null;
}

/** "De Lathauwer ILJ, Nieuwenhuys WW, et al." */
export function formatAuthors(authors: Author[], max = 2): string {
  const names = authors.map(authorName).filter((n): n is string => Boolean(n));
  if (names.length === 0) return "Authors not listed";
  if (names.length <= max + 1) return names.join(", ");
  return `${names.slice(0, max).join(", ")}, et al.`;
}

export const doiUrl = (doi: string) => `https://doi.org/${doi}`;

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

export function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** Project title from the first words of the draft. */
export function titleFromDraft(text: string, maxLength = 80): string {
  const firstLine = text.trim().split(/\n/)[0] ?? "";
  const cleaned = firstLine.replace(/\[[\d,\s–-]+\]/g, "").replace(/\s+/g, " ").trim();
  if (!cleaned) return "Untitled review";
  if (cleaned.length <= maxLength) return cleaned;
  const cut = cleaned.slice(0, maxLength);
  return `${cut.slice(0, cut.lastIndexOf(" ") > 40 ? cut.lastIndexOf(" ") : maxLength).trim()}…`;
}

export const pad2 = (n: number) => n.toString().padStart(2, "0");

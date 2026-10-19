/** Numbers in `text` that also appear in `reference` (e.g. "0.81" in a passage
 *  and a claim), as [start, end) ranges for <mark>. Purely a reading aid. */
const NUMBER = /\d+(?:\.\d+)?%?/g;

export function sharedNumberRanges(text: string, reference: string): [number, number][] {
  const wanted = new Set(Array.from(reference.matchAll(NUMBER), (m) => m[0].replace("%", "")));
  const ranges: [number, number][] = [];
  for (const match of text.matchAll(NUMBER)) {
    const value = match[0].replace("%", "");
    const index = match.index ?? 0;
    const before = text[index - 1] ?? "";
    // Skip digits that are part of a larger token (e.g. "I2", years inside words).
    if (/[\w.]/.test(before)) continue;
    if (wanted.has(value)) ranges.push([index, index + match[0].length]);
  }
  return ranges;
}

export interface TextSegment {
  text: string;
  marked: boolean;
}

export function segment(text: string, ranges: [number, number][]): TextSegment[] {
  const segments: TextSegment[] = [];
  let cursor = 0;
  for (const [start, end] of ranges) {
    if (start > cursor) segments.push({ text: text.slice(cursor, start), marked: false });
    segments.push({ text: text.slice(start, end), marked: true });
    cursor = end;
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor), marked: false });
  return segments;
}

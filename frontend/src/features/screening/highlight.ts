import type { Color, KeywordGroup } from "@/api/projects";

/**
 * Keyword highlighting (guide 8.5): one compiled pattern per keyword group, matched on
 * the client. Plain terms are escaped; pattern terms were checked by the server to be a
 * subset that cannot backtrack for ever, and means the same here as in Python. Text is
 * capped and each pattern has a time budget, so one bad group cannot freeze the screen.
 */
export interface Matcher {
  groupId: string;
  name: string;
  color: Color;
  pattern: RegExp;
}

export interface Segment {
  text: string;
  groupId?: string;
  color?: Color;
  name?: string;
}

const MAX_TEXT = 20_000;
const MAX_MATCHES = 2_000;
// A pattern that takes longer than this on one abstract is switched off for the record.
const BUDGET_MS = 30;

function escape(term: string): string {
  return term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function buildMatchers(groups: KeywordGroup[]): Matcher[] {
  const matchers: Matcher[] = [];
  for (const group of groups) {
    const parts = group.keywords
      .filter((keyword) => keyword.term.trim())
      .map((keyword) => {
        const body = keyword.is_regex ? keyword.term : escape(keyword.term.trim());
        return keyword.whole_word ? `(?<![\\p{L}\\p{N}])(?:${body})(?![\\p{L}\\p{N}])` : body;
      });
    if (parts.length === 0) continue;
    try {
      matchers.push({
        groupId: group.id,
        name: group.name,
        color: group.color,
        pattern: new RegExp(parts.join("|"), "giu"),
      });
    } catch {
      // A term the browser cannot compile is left out rather than breaking the screen.
    }
  }
  return matchers;
}

/** The text cut into plain and highlighted runs; the earliest, then longest, match wins. */
export function highlight(text: string, matchers: Matcher[]): Segment[] {
  if (!text || matchers.length === 0) return [{ text }];
  const subject = text.slice(0, MAX_TEXT);
  const hits: { start: number; end: number; matcher: Matcher }[] = [];
  for (const matcher of matchers) {
    const began = performance.now();
    matcher.pattern.lastIndex = 0;
    for (const match of subject.matchAll(matcher.pattern)) {
      if (match[0].length === 0) continue;
      hits.push({ start: match.index, end: match.index + match[0].length, matcher });
      if (hits.length > MAX_MATCHES || performance.now() - began > BUDGET_MS) break;
    }
  }
  hits.sort((a, b) => a.start - b.start || b.end - a.end);

  const segments: Segment[] = [];
  let cursor = 0;
  for (const hit of hits) {
    if (hit.start < cursor) continue; // overlaps a match already taken
    if (hit.start > cursor) segments.push({ text: subject.slice(cursor, hit.start) });
    segments.push({
      text: subject.slice(hit.start, hit.end),
      groupId: hit.matcher.groupId,
      color: hit.matcher.color,
      name: hit.matcher.name,
    });
    cursor = hit.end;
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor) });
  return segments;
}

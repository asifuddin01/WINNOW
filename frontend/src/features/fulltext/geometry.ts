import type { Matcher } from "@/features/screening/highlight";

/** A box on a page as fractions of the page: [x, y, width, height], each 0–1. */
export type Box = [number, number, number, number];

interface Rect {
  left: number;
  top: number;
  width: number;
  height: number;
}

const clamp = (value: number) => Math.min(1, Math.max(0, value));

/**
 * Screen rectangles of a selection, as fractions of its page, so a highlight stays in
 * place at any zoom. Rectangles on one line that touch are joined into one.
 */
export function toBoxes(rects: Iterable<Rect>, page: Rect): Box[] {
  if (page.width <= 0 || page.height <= 0) return [];
  const boxes: Box[] = [];
  for (const rect of rects) {
    if (rect.width < 1 || rect.height < 1) continue;
    const box: Box = [
      clamp((rect.left - page.left) / page.width),
      clamp((rect.top - page.top) / page.height),
      rect.width / page.width,
      rect.height / page.height,
    ];
    box[2] = Math.min(box[2], 1 - box[0]);
    box[3] = Math.min(box[3], 1 - box[1]);
    if (box[2] <= 0 || box[3] <= 0) continue;
    const last = boxes.at(-1);
    if (last && sameLine(last, box) && box[0] <= last[0] + last[2] + 0.005) {
      const right = Math.max(last[0] + last[2], box[0] + box[2]);
      const top = Math.min(last[1], box[1]);
      const bottom = Math.max(last[1] + last[3], box[1] + box[3]);
      last[0] = Math.min(last[0], box[0]);
      last[1] = top;
      last[2] = right - last[0];
      last[3] = bottom - top;
    } else {
      boxes.push(box);
    }
  }
  return boxes;
}

function sameLine(a: Box, b: Box): boolean {
  const overlap = Math.min(a[1] + a[3], b[1] + b[3]) - Math.max(a[1], b[1]);
  return overlap > 0.5 * Math.min(a[3], b[3]);
}

export interface KeywordBox {
  box: Box;
  color: Matcher["color"];
  name: string;
}

const MAX_KEYWORD_BOXES = 1_000;

/**
 * Where the review's keywords fall on one rendered page: each text run of pdf.js's text
 * layer is matched on its own, and the matches measured with a DOM Range. Nothing in the
 * text layer is changed, so selection and search keep working.
 */
export function keywordBoxes(textLayer: HTMLElement, page: Rect, matchers: Matcher[]) {
  const found: KeywordBox[] = [];
  if (matchers.length === 0) return found;
  const walker = document.createTreeWalker(textLayer, NodeFilter.SHOW_TEXT);
  const range = document.createRange();
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node.textContent ?? "";
    if (!text.trim()) continue;
    for (const matcher of matchers) {
      matcher.pattern.lastIndex = 0;
      for (const match of text.matchAll(matcher.pattern)) {
        if (match[0].length === 0) continue;
        range.setStart(node, match.index);
        range.setEnd(node, match.index + match[0].length);
        for (const box of toBoxes(Array.from(range.getClientRects()), page)) {
          found.push({ box, color: matcher.color, name: matcher.name });
        }
        if (found.length >= MAX_KEYWORD_BOXES) return found;
      }
    }
  }
  return found;
}

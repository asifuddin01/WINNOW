import { describe, expect, test } from "vitest";

import type { KeywordGroup } from "@/api/projects";
import { buildMatchers, highlight } from "@/features/screening/highlight";

function group(
  name: string,
  terms: { term: string; is_regex?: boolean; whole_word?: boolean }[],
  color: KeywordGroup["color"] = "green",
): KeywordGroup {
  return {
    id: name,
    name,
    color,
    kind: "include",
    keywords: terms.map((t, index) => ({
      id: `${name}-${index}`,
      group_id: name,
      term: t.term,
      is_regex: t.is_regex ?? false,
      whole_word: t.whole_word ?? true,
    })),
  };
}

function marked(text: string, groups: KeywordGroup[]): string[] {
  return highlight(text, buildMatchers(groups))
    .filter((segment) => segment.groupId)
    .map((segment) => segment.text);
}

describe("keyword highlighting", () => {
  test("plain terms are matched as words, whatever their case", () => {
    const groups = [group("Population", [{ term: "nurse" }, { term: "night shift" }])];
    expect(marked("Nurses and nurse managers on NIGHT SHIFT work", groups)).toEqual([
      "nurse",
      "NIGHT SHIFT",
    ]);
  });

  test("a term without whole-word matching finds it inside words", () => {
    const groups = [group("Stem", [{ term: "nurs", whole_word: false }])];
    expect(marked("Nursing and nurses", groups)).toEqual(["Nurs", "nurs"]);
  });

  test("characters that mean something in a pattern are taken literally in a plain term", () => {
    const groups = [group("Doses", [{ term: "C++ (v2)" }, { term: "a.b" }])];
    expect(marked("Tested C++ (v2) and axb, then a.b", groups)).toEqual(["C++ (v2)", "a.b"]);
  });

  test("pattern terms work, and accented letters count as letters for word edges", () => {
    const groups = [group("Kidney", [{ term: "renal|kidneys?", is_regex: true }])];
    expect(marked("Kidney and renal failure; not adrenal", groups)).toEqual(["Kidney", "renal"]);
    const accents = [group("Café", [{ term: "café" }])];
    expect(marked("café and cafés", accents)).toEqual(["café"]);
  });

  test("where two groups overlap, the earliest and then the longest match wins", () => {
    const groups = [
      group("Short", [{ term: "sleep" }], "blue"),
      group("Long", [{ term: "sleep quality" }], "red"),
    ];
    const segments = highlight("Poor sleep quality.", buildMatchers(groups));
    expect(segments.map((s) => [s.text, s.color ?? null])).toEqual([
      ["Poor ", null],
      ["sleep quality", "red"],
      [".", null],
    ]);
  });

  test("a term the browser cannot compile is left out rather than breaking the page", () => {
    const groups = [
      group("Broken", [{ term: "(unclosed", is_regex: true }]),
      group("Fine", [{ term: "ok" }]),
    ];
    expect(marked("it is ok", groups)).toEqual(["ok"]);
  });

  test("the text is always given back whole", () => {
    const groups = [group("Words", [{ term: "the" }])];
    const text = "the cat and the hat";
    expect(
      highlight(text, buildMatchers(groups))
        .map((s) => s.text)
        .join(""),
    ).toBe(text);
    expect(highlight(text, [])).toEqual([{ text }]);
  });
});

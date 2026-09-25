import { describe, expect, test } from "vitest";

import i18n, { LANGUAGES, preferredLanguage } from "@/i18n";
import common from "@/i18n/locales/en/common.json";

/** Every key in a catalogue, as the dotted path t() takes (plural forms folded). */
function keys(tree: object, prefix = ""): string[] {
  return Object.entries(tree).flatMap(([key, value]: [string, unknown]) =>
    value && typeof value === "object"
      ? keys(value, `${prefix}${key}.`)
      : [`${prefix}${key.replace(/_(one|other)$/, "")}`],
  );
}

describe("i18n", () => {
  test("the browser's first language Winnow speaks is chosen, else English", () => {
    expect(preferredLanguage(["en-GB", "bn"])).toBe("en");
    expect(preferredLanguage(["fr-FR", "EN-us"])).toBe("en");
    expect(preferredLanguage(["fr", "de"])).toBe("en");
    expect(preferredLanguage([])).toBe("en");
    expect(Object.keys(LANGUAGES)).toContain(i18n.language);
    expect(document.documentElement.lang).toBe("en");
  });

  test("every key in the English catalogue resolves to its text", () => {
    // Keys are typed; these come from walking the JSON, so they are plain strings.
    const t = i18n.t as (key: string, options: object) => string;
    for (const key of new Set(keys(common))) {
      const text = t(key, {
        count: 2,
        name: "x",
        email: "x",
        who: "x",
        review: "x",
        file: "x",
        excerpt: "x",
      });
      expect(text, key).not.toBe(key);
      expect(text, key).not.toContain("{{");
    }
  });

  test("plurals and numbers follow the language", () => {
    expect(i18n.t("palette.count", { count: 1 })).toMatch(/^1 result\./);
    expect(i18n.t("palette.count", { count: 3 })).toMatch(/^3 results\./);
    expect(i18n.t("notices.importFinished", { file: "a.ris", review: "R", count: 1500 })).toBe(
      "Your import of a.ris into R finished: 1,500 records",
    );
    expect(i18n.t("notices.importFinished", { file: "a.ris", review: "R", count: 1 })).toMatch(
      /1 record$/,
    );
  });
});

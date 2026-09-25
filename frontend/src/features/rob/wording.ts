/** Words for the answers the tools use (their keys come from `app.rob`). */
export const ANSWERS: Record<string, string> = {
  yes: "Yes",
  probably_yes: "Probably yes",
  probably_no: "Probably no",
  no: "No",
  no_information: "No information",
  not_applicable: "Not applicable",
  awarded: "Star awarded",
  not_awarded: "No star",
  unclear: "Unclear",
};

export const answerLabel = (key: string) => ANSWERS[key] ?? key.replaceAll("_", " ");

const MINUS = "−";
const TIMES = "×";

/** The plots' colours and symbols (robvis), so the page and the figures agree. */
const STYLE: Record<string, { fill: string; symbol: string; ink: string }> = {
  low: { fill: "#02C100", symbol: "+", ink: "#ffffff" },
  some_concerns: { fill: "#E2DF07", symbol: MINUS, ink: "#1f2933" },
  moderate: { fill: "#E2DF07", symbol: MINUS, ink: "#1f2933" },
  high: { fill: "#BF0000", symbol: TIMES, ink: "#ffffff" },
  serious: { fill: "#BF0000", symbol: TIMES, ink: "#ffffff" },
  critical: { fill: "#820000", symbol: "!", ink: "#ffffff" },
  unclear: { fill: "#4EA1F7", symbol: "?", ink: "#1f2933" },
  no_information: { fill: "#4EA1F7", symbol: "?", ink: "#1f2933" },
};

export function judgementStyle(key: string): { fill: string; symbol: string; ink: string } {
  if (key.startsWith("stars_")) {
    return { fill: "#d9e2ec", symbol: `${key.slice(6)}★`, ink: "#1f2933" };
  }
  return STYLE[key] ?? { fill: "#9aa5b1", symbol: "?", ink: "#1f2933" };
}

import { CheckIcon, CircleHelpIcon, XIcon } from "lucide-react";

import type { DecisionValue } from "@/api/screening";

export const DECISIONS: {
  value: DecisionValue;
  label: string;
  keys: string;
  icon: typeof CheckIcon;
  className: string;
}[] = [
  {
    value: "include",
    label: "Include",
    keys: "I or 1",
    icon: CheckIcon,
    className: "bg-include text-white hover:bg-include/90 dark:text-background",
  },
  {
    value: "maybe",
    label: "Maybe",
    keys: "M or 2",
    icon: CircleHelpIcon,
    className: "bg-maybe text-white hover:bg-maybe/90 dark:text-background",
  },
  {
    value: "exclude",
    label: "Exclude",
    keys: "E or 3",
    icon: XIcon,
    className: "bg-exclude text-white hover:bg-exclude/90 dark:text-background",
  },
];

export const DECIDED_TEXT: Record<DecisionValue, string> = {
  include: "Included",
  maybe: "Maybe",
  exclude: "Excluded",
};

/** Guide 11.4. */
export const SHORTCUTS: [string, string][] = [
  ["I or 1", "Include"],
  ["M or 2", "Maybe"],
  ["E or 3", "Exclude"],
  ["J or →", "Next record"],
  ["K or ←", "Previous record"],
  ["R", "Exclusion reasons, then a number to toggle one"],
  ["L", "Labels"],
  ["N", "Add a note"],
  ["F", "Focus mode"],
  ["H", "Keyword highlighting on or off"],
  ["/", "Search"],
  ["Ctrl/⌘ Z", "Undo the last decision"],
  ["?", "These shortcuts"],
];

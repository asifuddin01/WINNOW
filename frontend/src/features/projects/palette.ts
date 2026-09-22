import type { Color } from "@/api/projects";

/**
 * The colours a keyword group or label can take. The API stores the name, never a CSS
 * value, and each name maps to classes that stay readable in both themes (guide 11.3).
 * Colour never carries meaning on its own: every swatch sits beside its name.
 */
export const COLORS: Color[] = [
  "gray",
  "red",
  "orange",
  "amber",
  "green",
  "teal",
  "blue",
  "violet",
  "pink",
];

export const COLOR_NAMES: Record<Color, string> = {
  gray: "Grey",
  red: "Red",
  orange: "Orange",
  amber: "Amber",
  green: "Green",
  teal: "Teal",
  blue: "Blue",
  violet: "Violet",
  pink: "Pink",
};

/** Tailwind needs whole class names, so each one is written out. */
export const COLOR_CHIP: Record<Color, string> = {
  gray: "border-gray-500/30 bg-gray-500/10 text-gray-700 dark:text-gray-200",
  red: "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300",
  orange: "border-orange-500/30 bg-orange-500/10 text-orange-700 dark:text-orange-300",
  amber: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  green: "border-green-600/30 bg-green-600/10 text-green-700 dark:text-green-300",
  teal: "border-teal-600/30 bg-teal-600/10 text-teal-700 dark:text-teal-300",
  blue: "border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-300",
  violet: "border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-300",
  pink: "border-pink-500/30 bg-pink-500/10 text-pink-700 dark:text-pink-300",
};

export const COLOR_DOT: Record<Color, string> = {
  gray: "bg-gray-500",
  red: "bg-red-500",
  orange: "bg-orange-500",
  amber: "bg-amber-500",
  green: "bg-green-600",
  teal: "bg-teal-600",
  blue: "bg-blue-500",
  violet: "bg-violet-500",
  pink: "bg-pink-500",
};

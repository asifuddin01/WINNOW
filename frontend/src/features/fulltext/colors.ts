import type { AnnotationColor } from "@/api/fulltext";

/** Highlight colours. Each has a name beside its swatch; colour never stands alone. */
export const ANNOTATION_COLORS: AnnotationColor[] = ["yellow", "green", "blue", "pink"];

export const ANNOTATION_NAMES: Record<AnnotationColor, string> = {
  yellow: "Yellow",
  green: "Green",
  blue: "Blue",
  pink: "Pink",
};

/** Fills that let the printed text show through on the (always white) PDF page. */
export const ANNOTATION_FILL: Record<AnnotationColor, string> = {
  yellow: "bg-yellow-300",
  green: "bg-green-300",
  blue: "bg-sky-300",
  pink: "bg-pink-300",
};

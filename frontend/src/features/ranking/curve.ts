import type { Curve } from "@/api/ranking";

/** A line of the chart: who it is, and where each relevant record was found. */
export interface Series {
  key: string;
  label: string;
  curve: Curve;
}

/** How many relevant records a curve had found after `screened` records. */
export function foundAfter(curve: Curve, screened: number): number {
  let low = 0;
  let high = curve.found_at.length;
  while (low < high) {
    const middle = (low + high) >> 1;
    if ((curve.found_at[middle] ?? Infinity) <= screened) low = middle + 1;
    else high = middle;
  }
  return low;
}

/** Round, readable tick values from 0 up to the first at or above `max`, so the axis
 * always reaches the data. */
export function ticks(max: number, count = 5): number[] {
  if (max <= 0) return [0];
  const rough = max / count;
  const power = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 5, 10].map((m) => m * power).find((s) => s >= rough) ?? rough;
  const values: number[] = [];
  for (let value = 0; value < max + step; value += step) values.push(Math.round(value));
  return values;
}

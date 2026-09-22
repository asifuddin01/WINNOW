import { CheckIcon } from "lucide-react";

import type { Color } from "@/api/projects";
import { COLOR_DOT, COLOR_NAMES, COLORS } from "@/features/projects/palette";
import { cn } from "@/lib/utils";

/** A row of swatches, each keyboard reachable and named for screen readers. */
export function ColorChoice({
  value,
  onChange,
  label = "Colour",
}: {
  value: Color;
  onChange: (color: Color) => void;
  label?: string;
}) {
  return (
    <fieldset className="grid gap-1.5">
      <legend className="text-sm font-medium">{label}</legend>
      <div className="flex flex-wrap gap-1.5">
        {COLORS.map((color) => (
          <label
            key={color}
            className={cn(
              "flex size-8 cursor-pointer items-center justify-center rounded-full border-2 border-transparent text-white transition-colors has-[:checked]:border-foreground has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring/50",
              COLOR_DOT[color],
            )}
          >
            <input
              type="radio"
              name={`colour-${label}`}
              value={color}
              checked={value === color}
              onChange={() => {
                onChange(color);
              }}
              className="sr-only"
            />
            <span className="sr-only">{COLOR_NAMES[color]}</span>
            {value === color && <CheckIcon className="size-4" aria-hidden="true" />}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

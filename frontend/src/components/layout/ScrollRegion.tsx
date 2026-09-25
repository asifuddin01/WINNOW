import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * A box that scrolls sideways when what it holds (a table, a plot) is wider than the
 * screen. It takes focus, so keyboard users can scroll it with the arrow keys (axe
 * scrollable-region-focusable), and it is a named region, so they know what they reached.
 */
export function ScrollRegion({
  label,
  className,
  children,
}: {
  label: string;
  className?: string;
  children: ReactNode;
}) {
  /* eslint-disable jsx-a11y/no-noninteractive-tabindex -- see above: a region that
     scrolls has to be reachable, which this rule forbids. */
  return (
    <div
      tabIndex={0}
      role="region"
      aria-label={label}
      className={cn(
        "overflow-x-auto focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
        className,
      )}
    >
      {children}
    </div>
  );
  /* eslint-enable jsx-a11y/no-noninteractive-tabindex */
}

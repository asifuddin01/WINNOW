import { WheatIcon } from "lucide-react";

import { cn } from "@/lib/utils";

/** The wheat mark in a teal tile, with the lowercase "winnow" wordmark (guide 19.1). */
export function BrandMark({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground",
        className,
      )}
    >
      <WheatIcon className="size-4.5" strokeWidth={2.25} />
    </span>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("text-lg leading-none font-semibold tracking-tight", className)}>
      winnow
    </span>
  );
}

import { useQuery } from "@tanstack/react-query";
import { SignpostIcon } from "lucide-react";
import { useId, useState } from "react";

import { stoppingQuery } from "@/api/ranking";
import type { Stage } from "@/api/screening";
import { Button } from "@/components/ui/button";

/**
 * Guide 8.5's stopping-rule helper: once a reviewer has excluded the review's number of
 * records in a row, say so and estimate what is left. Advice only; it never stops anyone.
 */
export function StoppingBanner({ pid, stage }: { pid: string; stage: Stage }) {
  const { data: advice } = useQuery(stoppingQuery(pid, stage));
  // "Keep screening" puts it away until another run of the same length.
  const [dismissedAt, setDismissedAt] = useState<number | null>(null);
  const titleId = useId();
  if (!advice?.estimate) return null;
  if (dismissedAt !== null && advice.in_a_row < dismissedAt + advice.threshold) return null;
  const { expected, low, high } = advice.estimate;

  return (
    <section
      aria-labelledby={titleId}
      className="grid gap-2 rounded-md border bg-card px-4 py-3 text-sm"
    >
      <h2 id={titleId} className="flex items-center gap-2 font-semibold">
        <SignpostIcon className="size-4" aria-hidden="true" />
        You have excluded {advice.in_a_row.toLocaleString()} records in a row
      </h2>
      <p>
        Estimated relevant records still among the {advice.remaining.toLocaleString()} you have not
        screened: about {Math.round(expected).toLocaleString()} (likely {low.toLocaleString()}–
        {high.toLocaleString()}).
      </p>
      <p className="text-muted-foreground">
        This is advice. Whether to stop is the review team&apos;s decision, to report in your
        methods; Winnow never stops screening for you.
      </p>
      <details>
        <summary className="cursor-pointer text-xs font-medium text-primary">
          How this is estimated
        </summary>
        <p className="mt-1 max-w-[75ch] text-xs text-muted-foreground">
          Screening in relevance order finds relevant records more and more rarely. Winnow fits the
          rate at which your decisions in relevance order have found them as a decaying curve and
          carries it on over the records you have not screened; the range comes from refitting to
          many simulated histories like yours. Tested on 21 published reviews, it held the true
          number left 96% of the time. It assumes relevant records keep getting rarer, so treat it
          with caution if the search or the criteria changed.
        </p>
      </details>
      <div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            setDismissedAt(advice.in_a_row);
          }}
        >
          Keep screening
        </Button>
      </div>
    </section>
  );
}

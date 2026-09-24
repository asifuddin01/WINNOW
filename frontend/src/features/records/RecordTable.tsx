import { useInfiniteQuery } from "@tanstack/react-query";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useEffect, useRef } from "react";

import { recordsQuery, type Record as ReviewRecord, type RecordQuery } from "@/api/records";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const ROW_HEIGHT = 92;
const OVERSCAN = 8;

const TA_LABEL: Record<string, string> = {
  pending: "Not screened",
  included: "Included",
  excluded: "Excluded",
  maybe: "Maybe",
  conflict: "Conflict",
};

/**
 * The records table. Long lists are virtualised (guide 11.5) and the next page is fetched
 * as the end comes into view, so 100,000 records scroll like 50.
 */
export function RecordTable({
  pid,
  query,
  selected,
  onSelect,
}: {
  pid: string;
  query: RecordQuery;
  selected: string | null;
  onSelect: (record: ReviewRecord) => void;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  const { data, isPending, fetchNextPage, hasNextPage, isFetchingNextPage } = useInfiniteQuery(
    recordsQuery(pid, query),
  );
  const records = data?.pages.flatMap((page) => page.items) ?? [];
  const total = data?.pages[0]?.total ?? 0;
  const exact = data?.pages[0]?.total_is_exact ?? true;

  // The compiler cannot memoise a virtualiser's callbacks; that is the point of it.
  // eslint-disable-next-line react-hooks/incompatible-library
  const virtualizer = useVirtualizer({
    count: records.length,
    getScrollElement: () => scroller.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: OVERSCAN,
  });

  const items = virtualizer.getVirtualItems();
  const last = items.at(-1)?.index ?? 0;
  useEffect(() => {
    if (hasNextPage && !isFetchingNextPage && last >= records.length - OVERSCAN) {
      void fetchNextPage();
    }
  }, [hasNextPage, isFetchingNextPage, last, records.length, fetchNextPage]);

  if (isPending) {
    return (
      <div className="grid gap-2" aria-busy="true">
        {[0, 1, 2, 3].map((key) => (
          <Skeleton key={key} className="h-20 w-full rounded-lg" />
        ))}
      </div>
    );
  }

  if (records.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-input p-8 text-center text-sm text-muted-foreground">
        No records match. Try fewer words, or clear the filters.
      </p>
    );
  }

  return (
    <div className="grid gap-2">
      <p className="text-sm text-muted-foreground" role="status">
        {total.toLocaleString()}
        {exact ? "" : "+"} record{total === 1 ? "" : "s"}
      </p>
      {/* eslint-disable jsx-a11y/no-noninteractive-tabindex -- a scrollable region has to be
          keyboard reachable (axe scrollable-region-focusable), which this rule forbids. */}
      <div
        ref={scroller}
        className="h-[60vh] overflow-auto rounded-lg border border-border"
        tabIndex={0}
        role="region"
        aria-label="Records"
      >
        {/* eslint-enable jsx-a11y/no-noninteractive-tabindex */}
        <ul style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
          {items.map((item) => {
            const record = records[item.index];
            if (!record) return null;
            return (
              <li
                key={record.id}
                data-index={item.index}
                className="absolute inset-x-0"
                style={{ transform: `translateY(${item.start}px)` }}
              >
                <RecordRow
                  record={record}
                  active={record.id === selected}
                  onSelect={() => {
                    onSelect(record);
                  }}
                />
              </li>
            );
          })}
        </ul>
      </div>
      {isFetchingNextPage && <p className="text-xs text-muted-foreground">Loading more records…</p>}
    </div>
  );
}

function RecordRow({
  record,
  active,
  onSelect,
}: {
  record: ReviewRecord;
  active: boolean;
  onSelect: () => void;
}) {
  const meta = [
    record.authors.slice(0, 3).join("; "),
    record.year,
    record.journal,
    record.relevance_score !== null && `Relevance ${Math.round(record.relevance_score * 100)}%`,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={active ? "true" : undefined}
      className={cn(
        "grid w-full gap-1 border-b border-border px-4 py-3 text-left transition-colors hover:bg-muted/50 focus-visible:bg-muted/50 focus-visible:outline-none",
        active && "bg-muted",
      )}
    >
      <span className="flex items-start gap-2">
        <span className="line-clamp-2 flex-1 text-sm font-medium">
          {record.title ?? "(no title)"}
        </span>
        <Badge variant={record.ta_final === "pending" ? "outline" : "secondary"}>
          {TA_LABEL[record.ta_final] ?? record.ta_final}
        </Badge>
      </span>
      <span className="line-clamp-1 text-xs text-muted-foreground">{meta}</span>
      {record.doi && <span className="font-mono text-xs text-muted-foreground">{record.doi}</span>}
    </button>
  );
}

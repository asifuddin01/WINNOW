import { useQuery } from "@tanstack/react-query";
import { EyeIcon, EyeOffIcon } from "lucide-react";

import type { KeywordGroup } from "@/api/projects";
import { historyQuery, type Stage } from "@/api/screening";
import { Skeleton } from "@/components/ui/skeleton";
import { COLOR_DOT } from "@/features/projects/palette";
import { DECIDED_TEXT, SHORTCUTS } from "@/features/screening/wording";
import { cn } from "@/lib/utils";

/** Which keyword groups are highlighted; each can be switched off (guide 8.5). */
export function KeywordLegend({
  groups,
  hidden,
  enabled,
  onToggle,
}: {
  groups: KeywordGroup[];
  hidden: string[];
  enabled: boolean;
  onToggle: (groupId: string) => void;
}) {
  const withTerms = groups.filter((group) => group.keywords.length > 0);
  if (withTerms.length === 0) return null;
  return (
    <section aria-labelledby="keyword-legend" className="grid gap-1.5">
      <h2 id="keyword-legend" className="text-xs font-semibold text-muted-foreground uppercase">
        Highlighting {enabled ? "" : "(off — H)"}
      </h2>
      <ul className="grid gap-1">
        {withTerms.map((group) => {
          const on = enabled && !hidden.includes(group.id);
          return (
            <li key={group.id}>
              <button
                type="button"
                aria-pressed={on}
                disabled={!enabled}
                onClick={() => {
                  onToggle(group.id);
                }}
                className={cn(
                  "flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-sm hover:bg-muted disabled:opacity-60",
                  !on && "text-muted-foreground",
                )}
              >
                <span
                  className={cn("size-2.5 rounded-full", COLOR_DOT[group.color])}
                  aria-hidden="true"
                />
                <span className="flex-1 truncate">{group.name}</span>
                {on ? (
                  <EyeIcon className="size-3.5" aria-hidden="true" />
                ) : (
                  <EyeOffIcon className="size-3.5" aria-hidden="true" />
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** My recent decisions; any can be opened again and changed (guide 8.5). */
export function HistoryPanel({
  pid,
  stage,
  onOpen,
}: {
  pid: string;
  stage: Stage;
  onOpen: (recordId: string) => void;
}) {
  const { data, isPending } = useQuery(historyQuery(pid, stage));
  if (isPending) return <Skeleton className="h-40 w-full" />;
  const items = data?.items ?? [];
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">Your decisions will be listed here.</p>;
  }
  return (
    <ol className="grid gap-1">
      {items.map((item) => (
        <li key={item.record_id}>
          <button
            type="button"
            onClick={() => {
              onOpen(item.record_id);
            }}
            className="grid w-full gap-0.5 rounded-md px-2 py-1.5 text-left hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            <span className="line-clamp-2 text-sm">{item.title ?? "(no title)"}</span>
            <span
              className={cn(
                "text-xs font-medium",
                item.decision === "include" && "text-include",
                item.decision === "exclude" && "text-exclude",
                item.decision === "maybe" && "text-maybe",
              )}
            >
              {DECIDED_TEXT[item.decision]}
              {item.year ? <span className="text-muted-foreground"> · {item.year}</span> : null}
            </span>
          </button>
        </li>
      ))}
    </ol>
  );
}

export function ShortcutList() {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
      {SHORTCUTS.map(([keys, action]) => (
        <div key={keys} className="contents">
          <dt>
            <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-xs">
              {keys}
            </kbd>
          </dt>
          <dd>{action}</dd>
        </div>
      ))}
    </dl>
  );
}

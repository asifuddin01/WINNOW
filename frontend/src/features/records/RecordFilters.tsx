import { useQuery } from "@tanstack/react-query";

import { facetsQuery, type RecordQuery } from "@/api/records";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** The counts beside the filters, from the facets endpoint (guide 10). */
export function RecordFilters({
  pid,
  query,
  onChange,
}: {
  pid: string;
  query: RecordQuery;
  onChange: (next: RecordQuery) => void;
}) {
  const { data: facets } = useQuery(facetsQuery(pid));
  if (!facets) return null;

  const statuses = facets.title_abstract;
  const total = facets.total;

  return (
    <nav aria-label="Filters" className="grid content-start gap-4 text-sm">
      <section aria-labelledby="filter-status" className="grid gap-1">
        <h2 id="filter-status" className="text-xs font-semibold text-muted-foreground uppercase">
          Screening
        </h2>
        <FilterButton
          label="All records"
          count={total}
          active={!query.status}
          onClick={() => {
            onChange({ ...query, status: undefined });
          }}
        />
        {statuses.map((count) => (
          <FilterButton
            key={count.value}
            label={count.label}
            count={count.count}
            active={query.status === count.value}
            onClick={() => {
              onChange({ ...query, status: count.value as RecordQuery["status"] });
            }}
          />
        ))}
      </section>

      {facets.imports.length > 0 && (
        <section aria-labelledby="filter-import" className="grid gap-1">
          <h2 id="filter-import" className="text-xs font-semibold text-muted-foreground uppercase">
            Import
          </h2>
          {facets.imports.map((count) => (
            <FilterButton
              key={count.value}
              label={count.label}
              count={count.count}
              active={query.batch === count.value}
              onClick={() => {
                onChange({
                  ...query,
                  batch: query.batch === count.value ? undefined : count.value,
                });
              }}
            />
          ))}
        </section>
      )}

      {facets.years.length > 0 && (
        <section aria-labelledby="filter-year" className="grid gap-1">
          <h2 id="filter-year" className="text-xs font-semibold text-muted-foreground uppercase">
            Year
          </h2>
          <div className="flex flex-wrap gap-1">
            {[...facets.years]
              .sort((a, b) => Number(b.value) - Number(a.value))
              .map((count) => (
                <Button
                  key={count.value}
                  size="sm"
                  variant="ghost"
                  className="h-7 px-2 text-xs"
                  onClick={() => {
                    onChange({ ...query, q: `year:${count.value}` });
                  }}
                >
                  {count.label}
                  <span className="text-muted-foreground">{count.count}</span>
                </Button>
              ))}
          </div>
        </section>
      )}

      {facets.duplicates > 0 && (
        <FilterButton
          label="Duplicates"
          count={facets.duplicates}
          active={Boolean(query.duplicates)}
          onClick={() => {
            onChange({ ...query, duplicates: !query.duplicates });
          }}
        />
      )}
    </nav>
  );
}

function FilterButton({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "flex items-center justify-between gap-2 rounded-md px-2 py-1 text-left hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
        active && "bg-muted font-medium",
      )}
    >
      <span className="truncate capitalize">{label}</span>
      <span className="text-xs text-muted-foreground">{count.toLocaleString()}</span>
    </button>
  );
}

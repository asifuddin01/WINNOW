import { useQuery } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { SearchIcon } from "lucide-react";
import { useState } from "react";

import { projectQuery } from "@/api/projects";
import type { RecordQuery, Sort } from "@/api/records";
import { SelectField } from "@/components/forms/SelectField";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RecordDetailPanel } from "@/features/records/RecordDetailPanel";
import { RecordFilters } from "@/features/records/RecordFilters";
import { RecordTable } from "@/features/records/RecordTable";
import { recordsSearch } from "@/lib/search";

export const Route = createFileRoute("/_app/p/$pid/records")({
  validateSearch: recordsSearch,
  component: RecordsPage,
  staticData: { title: "Records" },
});

const SORTS: { value: Sort; label: string }[] = [
  { value: "added", label: "Newest first" },
  { value: "oldest", label: "Oldest first" },
  { value: "year", label: "Year, newest" },
  { value: "year_asc", label: "Year, oldest" },
  { value: "title", label: "Title A–Z" },
];

const SYNTAX =
  '"exact phrase" · -exclude · author:smith · journal:BMJ · year:2018..2024 · a DOI or PubMed id';

function RecordsPage() {
  const { pid } = Route.useParams();
  const search = Route.useSearch();
  const navigate = useNavigate();
  const { data: project } = useQuery(projectQuery(pid));
  const [typed, setTyped] = useState(search.q ?? "");
  const [selected, setSelected] = useState<string | null>(null);

  const query: RecordQuery = {
    q: search.q,
    status: search.status,
    batch: search.batch,
    duplicates: search.duplicates,
    sort: search.sort ?? "added",
  };
  const update = (next: RecordQuery) => {
    setTyped(next.q ?? "");
    void navigate({
      to: "/p/$pid/records",
      params: { pid },
      search: {
        ...(next.q ? { q: next.q } : {}),
        ...(next.status ? { status: next.status } : {}),
        ...(next.batch ? { batch: next.batch } : {}),
        ...(next.duplicates ? { duplicates: true } : {}),
        ...(next.sort && next.sort !== "added" ? { sort: next.sort } : {}),
      },
      replace: true,
    });
  };

  if (!project) return null;

  return (
    <div className="mx-auto grid w-full max-w-7xl gap-6 px-4 py-8 md:px-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Records</h1>
          <p className="mt-1 text-muted-foreground">
            Everything imported into this review, searchable and filterable.
          </p>
        </div>
        <SelectField
          label="Order"
          className="w-44"
          value={query.sort ?? "added"}
          options={SORTS}
          onChange={(sort) => {
            update({ ...query, sort });
          }}
        />
      </div>

      <form
        className="grid gap-1.5"
        onSubmit={(event) => {
          event.preventDefault();
          update({ ...query, q: typed.trim() || undefined });
        }}
      >
        <Label htmlFor="record-search">Search</Label>
        <div className="flex gap-2">
          <Input
            id="record-search"
            value={typed}
            placeholder='sleep quality "night shift" -paediatric author:smith'
            aria-describedby="search-syntax"
            onChange={(event) => {
              setTyped(event.target.value);
            }}
          />
          <Button type="submit">
            <SearchIcon aria-hidden="true" /> Search
          </Button>
          {search.q && (
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                update({ ...query, q: undefined });
              }}
            >
              Clear
            </Button>
          )}
        </div>
        <p id="search-syntax" className="text-xs text-muted-foreground">
          {SYNTAX}
        </p>
      </form>

      <div className="grid gap-6 lg:grid-cols-[13rem_1fr]">
        <RecordFilters pid={pid} query={query} onChange={update} />
        <div className="grid gap-4 xl:grid-cols-2">
          <RecordTable
            pid={pid}
            query={query}
            selected={selected}
            onSelect={(record) => {
              setSelected(record.id);
            }}
          />
          {selected ? (
            <RecordDetailPanel pid={pid} rid={selected} />
          ) : (
            <p className="hidden rounded-xl border border-dashed border-input p-8 text-center text-sm text-muted-foreground xl:block">
              Choose a record to read its abstract.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

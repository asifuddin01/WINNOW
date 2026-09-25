import { useQuery } from "@tanstack/react-query";
import { DownloadIcon, PlusIcon, Trash2Icon } from "lucide-react";
import { useId, useState, type SyntheticEvent } from "react";

import { ApiError, errorMessage } from "@/api/client";
import {
  prismaQuery,
  prismaUrl,
  reportKeys,
  updatePrismaManual,
  type Prisma,
  type PrismaFormat,
} from "@/api/reporting";
import { FormAlert } from "@/components/forms/FormAlert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useProjectMutation } from "@/features/projects/use-project-mutation";

const FORMATS: { format: PrismaFormat; label: string }[] = [
  { format: "svg", label: "SVG" },
  { format: "png", label: "PNG (300 dpi)" },
  { format: "pdf", label: "PDF" },
];

const n = (value: number) => value.toLocaleString();

export function PrismaView({ pid, canEdit }: { pid: string; canEdit: boolean }) {
  const { data: flow, error, isPending, dataUpdatedAt } = useQuery(prismaQuery(pid));

  if (isPending) return <Skeleton className="h-[36rem] w-full rounded-xl" aria-busy="true" />;
  if (error) {
    return (
      <div className="grid gap-6">
        <FormAlert>
          {error instanceof ApiError && error.code === "prisma_inconsistent"
            ? `The numbers do not add up, so the diagram is not drawn: ${error.message}`
            : errorMessage(error)}
        </FormAlert>
        {canEdit && <ManualCounts pid={pid} flow={null} />}
      </div>
    );
  }

  const waiting = flow.awaiting_title_abstract + flow.awaiting_full_text;
  return (
    <div className="grid gap-6">
      {waiting > 0 && (
        <FormAlert tone="warning">
          Screening is not finished, so this is a snapshot: {n(flow.awaiting_title_abstract)}{" "}
          {flow.awaiting_title_abstract === 1 ? "record waits" : "records wait"} at title and
          abstract, and {n(flow.awaiting_full_text)} at full text.
        </FormAlert>
      )}

      <figure className="grid gap-3">
        {/* eslint-disable jsx-a11y/no-noninteractive-tabindex -- a scrollable region has to be
          keyboard reachable (axe scrollable-region-focusable), which this rule forbids. */}
        <div
          tabIndex={0}
          role="region"
          aria-label="PRISMA 2020 flow diagram"
          className="overflow-x-auto rounded-xl border border-border bg-white dark:brightness-90 p-4 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
        >
          {/* eslint-enable jsx-a11y/no-noninteractive-tabindex */}
          {/* The server draws the diagram, the same one the downloads carry. */}
          <img
            src={`${prismaUrl(pid, "svg", true)}&v=${dataUpdatedAt}`}
            alt="PRISMA 2020 flow diagram. Its numbers are listed below."
            className="mx-auto h-auto w-full max-w-3xl min-w-[36rem]"
          />
        </div>
        <figcaption className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <span className="mr-auto">PRISMA 2020 flow diagram, counted from the review.</span>
          {FORMATS.map(({ format, label }) => (
            <Button key={format} asChild variant="outline" size="sm">
              <a href={prismaUrl(pid, format)} download>
                <DownloadIcon aria-hidden="true" />
                {label}
              </a>
            </Button>
          ))}
        </figcaption>
      </figure>

      <FlowNumbers flow={flow} />
      {canEdit && <ManualCounts pid={pid} flow={flow} />}
    </div>
  );
}

/** The diagram's numbers as text, for reading aloud and for copying. */
function FlowNumbers({ flow }: { flow: Prisma }) {
  const rows: [string, number][] = [
    ...flow.database_sources.map((source): [string, number] => [
      `Records from ${source.name}`,
      source.count,
    ]),
    ...flow.other_sources.map((source): [string, number] => [
      `Records from ${source.name} (other sources)`,
      source.count,
    ]),
    ["Records identified", flow.records_identified],
    ["Duplicate records removed", flow.duplicates_removed],
    ["Records removed for other reasons", flow.records_removed_other_reasons],
    ["Records screened", flow.records_screened],
    ["Records excluded", flow.records_excluded],
    ["Reports sought for retrieval", flow.reports_sought],
    ["Reports not retrieved", flow.reports_not_retrieved],
    ["Reports assessed for eligibility", flow.reports_assessed],
    ...flow.reports_excluded.map((reason): [string, number] => [
      `Reports excluded: ${reason.reason}`,
      reason.count,
    ]),
    ["Studies included in review", flow.studies_included],
  ];
  return (
    <details className="rounded-xl border border-border bg-card">
      <summary className="cursor-pointer px-4 py-3 text-sm font-medium">
        The numbers in the diagram
      </summary>
      <table className="w-full text-sm">
        <caption className="sr-only">PRISMA 2020 counts</caption>
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label} className="border-t border-border">
              <th scope="row" className="px-4 py-2 text-left font-normal">
                {label}
              </th>
              <td className="px-4 py-2 text-right tabular-nums">{n(value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

interface SourceRow {
  key: number;
  name: string;
  count: string;
}

/** What Winnow cannot count: records from other sources, and removals before screening. */
function ManualCounts({ pid, flow }: { pid: string; flow: Prisma | null }) {
  const id = useId();
  const manual = flow?.manual;
  const [sources, setSources] = useState<SourceRow[]>(() =>
    (manual?.other_sources ?? []).map((source, key) => ({
      key,
      name: source.name,
      count: String(source.count),
    })),
  );
  const [removed, setRemoved] = useState(String(manual?.removed_other_reasons ?? 0));
  const [problem, setProblem] = useState<string | null>(null);
  const save = useProjectMutation(
    () =>
      updatePrismaManual(pid, {
        other_sources: sources
          .filter((row) => row.name.trim())
          .map((row) => ({ name: row.name.trim(), count: Number(row.count) })),
        removed_other_reasons: Number(removed),
      }),
    { invalidate: [reportKeys.prisma(pid)], success: "Saved. The diagram is up to date." },
  );

  const whole = (value: string) => /^\d{1,9}$/.test(value.trim());
  const onSubmit = (event: SyntheticEvent) => {
    event.preventDefault();
    const bad = sources.find((row) => row.name.trim() && !whole(row.count));
    const names = sources.map((row) => row.name.trim().toLowerCase()).filter(Boolean);
    const found = bad
      ? `Give ${bad.name.trim()} a whole number of records.`
      : !whole(removed)
        ? "Records removed before screening must be a whole number."
        : new Set(names).size !== names.length
          ? "Each source needs its own name."
          : null;
    setProblem(found);
    if (found) return;
    save.mutate(undefined);
  };

  return (
    <section
      aria-labelledby={`${id}-title`}
      className="grid gap-4 rounded-xl border border-border bg-card p-5"
    >
      <div>
        <h2 id={`${id}-title`} className="text-lg font-medium">
          What Winnow cannot count
        </h2>
        <p className="text-sm text-muted-foreground">
          Records found outside the imported databases, such as citation searching or websites, and
          records removed before screening for other reasons, such as an automation tool. Everything
          else in the diagram comes from the review itself.
        </p>
      </div>
      <form className="grid gap-4" onSubmit={onSubmit} noValidate>
        <fieldset className="grid gap-2">
          <legend className="mb-1 text-sm font-medium">Other sources</legend>
          {sources.length === 0 && (
            <p className="text-sm text-muted-foreground">
              None. Add one if you searched elsewhere.
            </p>
          )}
          {sources.map((row, index) => (
            <div key={row.key} className="flex flex-wrap items-end gap-2">
              <div className="grid min-w-48 flex-1 gap-1">
                <Label htmlFor={`${id}-name-${row.key}`}>Source {index + 1}</Label>
                <Input
                  id={`${id}-name-${row.key}`}
                  value={row.name}
                  maxLength={200}
                  placeholder="Citation searching"
                  onChange={(event) => {
                    setSources((all) =>
                      all.map((r) => (r.key === row.key ? { ...r, name: event.target.value } : r)),
                    );
                  }}
                />
              </div>
              <div className="grid w-32 gap-1">
                <Label htmlFor={`${id}-count-${row.key}`}>Records</Label>
                <Input
                  id={`${id}-count-${row.key}`}
                  inputMode="numeric"
                  value={row.count}
                  onChange={(event) => {
                    setSources((all) =>
                      all.map((r) => (r.key === row.key ? { ...r, count: event.target.value } : r)),
                    );
                  }}
                />
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={`Remove source ${index + 1}`}
                onClick={() => {
                  setSources((all) => all.filter((r) => r.key !== row.key));
                }}
              >
                <Trash2Icon aria-hidden="true" />
              </Button>
            </div>
          ))}
          <div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                setSources((all) => [
                  ...all,
                  { key: Math.max(-1, ...all.map((r) => r.key)) + 1, name: "", count: "0" },
                ]);
              }}
            >
              <PlusIcon aria-hidden="true" /> Add a source
            </Button>
          </div>
        </fieldset>
        <div className="grid w-full max-w-xs gap-1">
          <Label htmlFor={`${id}-removed`}>Records removed before screening, other reasons</Label>
          <Input
            id={`${id}-removed`}
            inputMode="numeric"
            value={removed}
            onChange={(event) => {
              setRemoved(event.target.value);
            }}
          />
        </div>
        {(problem ?? (save.isError ? errorMessage(save.error) : null)) && (
          <FormAlert>{problem ?? errorMessage(save.error)}</FormAlert>
        )}
        <div>
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save counts"}
          </Button>
        </div>
      </form>
    </section>
  );
}

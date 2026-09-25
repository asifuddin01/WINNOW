import { useQuery } from "@tanstack/react-query";
import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import { CheckIcon, ScaleIcon } from "lucide-react";
import { useState } from "react";

import { ApiError, errorMessage } from "@/api/client";
import {
  consensusQuery,
  extractionKeys,
  formsQuery,
  saveConsensus,
  schemaOf,
  studiesQuery,
  type ConsensusView,
  type EntryData,
  type ExtractionForm,
} from "@/api/extraction";
import { projectQuery } from "@/api/projects";
import { FormAlert } from "@/components/forms/FormAlert";
import { ScrollRegion } from "@/components/layout/ScrollRegion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EntryFields } from "@/features/extraction/EntryFields";
import { withValue } from "@/features/extraction/fields";
import { FormPicker } from "@/features/extraction/FormPicker";
import { useProjectMutation } from "@/features/projects/use-project-mutation";
import { extractionSearch } from "@/lib/search";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/p/$pid/extraction/consensus")({
  validateSearch: extractionSearch,
  component: ConsensusPage,
  staticData: { title: "Consensus" },
});

function shown(value: unknown): string {
  if (value === null || value === undefined || value === "") return "(empty)";
  if (Array.isArray(value)) return value.join("; ");
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

function ConsensusPage() {
  const { pid } = Route.useParams();
  const { form: chosen, study } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const { data: project } = useQuery(projectQuery(pid));
  const { data: forms, isPending } = useQuery(formsQuery(pid));
  const usable = (forms ?? []).filter((form) => form.published);
  const form =
    usable.find((f) => f.id === chosen) ?? usable.findLast((f) => f.dual) ?? usable.at(-1);

  if (isPending || !project)
    return <Skeleton className="h-64 w-full rounded-xl" aria-busy="true" />;
  if (!project.permissions.includes("resolve_conflicts")) {
    return (
      <p className="text-sm text-muted-foreground">
        Consensus is for those who resolve conflicts in this review.
      </p>
    );
  }
  if (!form) return <p className="text-sm text-muted-foreground">No published form yet.</p>;
  return (
    <div className="grid gap-5">
      <FormPicker
        forms={usable}
        value={form.id}
        onChange={(next) => {
          void navigate({ search: { form: next } });
        }}
      />
      <div className="grid gap-6 lg:grid-cols-[18rem_1fr]">
        <Waiting pid={pid} form={form} selected={study} />
        <div className="min-w-0">
          {study ? (
            <Reconcile key={`${form.id}:${study}`} pid={pid} form={form} rid={study} />
          ) : (
            <p className="rounded-xl border border-dashed border-input p-6 text-center text-sm text-muted-foreground">
              Choose a study extracted by more than one person.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function Waiting({
  pid,
  form,
  selected,
}: {
  pid: string;
  form: ExtractionForm;
  selected: string | undefined;
}) {
  const { data: studies, isPending } = useQuery(studiesQuery(pid, form.id));
  if (isPending) return <Skeleton className="h-64 w-full rounded-xl" aria-busy="true" />;
  const twice = (studies ?? []).filter((s) => (s.submitted ?? 0) > 1);
  if (twice.length === 0) {
    return (
      <p className="grid justify-items-center gap-2 rounded-xl border border-dashed border-input p-6 text-center text-sm text-muted-foreground">
        <ScaleIcon className="size-6" aria-hidden="true" />
        Nothing to reconcile: no study has two submitted extractions yet.
      </p>
    );
  }
  return (
    <nav aria-label="Studies to reconcile" className="grid content-start gap-2">
      <p className="text-sm text-muted-foreground">
        {twice.filter((s) => !s.consensus).length} of {twice.length} still to reconcile.
      </p>
      <ul className="grid gap-1">
        {twice.map((item) => (
          <li key={item.record_id}>
            <Link
              to="/p/$pid/extraction/consensus"
              params={{ pid }}
              search={{ form: form.id, study: item.record_id }}
              aria-current={selected === item.record_id ? "page" : undefined}
              className={cn(
                "grid gap-0.5 rounded-lg border border-transparent px-3 py-2 text-sm hover:bg-muted",
                "focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
                selected === item.record_id && "border-border bg-muted",
              )}
            >
              <span className="font-medium">{item.label}</span>
              <span className="flex gap-1 pt-0.5">
                <Badge variant={item.consensus ? "default" : "secondary"}>
                  {item.consensus ? "Reconciled" : `${item.submitted} extractions`}
                </Badge>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function Reconcile({ pid, form, rid }: { pid: string; form: ExtractionForm; rid: string }) {
  const { data, error, isPending } = useQuery(consensusQuery(pid, form.id, rid));
  if (isPending) return <Skeleton className="h-96 w-full rounded-xl" aria-busy="true" />;
  if (error) return <FormAlert>{errorMessage(error)}</FormAlert>;
  return (
    <Editor key={data.consensus?.updated_at ?? "new"} pid={pid} form={form} rid={rid} view={data} />
  );
}

function Editor({
  pid,
  form,
  rid,
  view,
}: {
  pid: string;
  form: ExtractionForm;
  rid: string;
  view: ConsensusView;
}) {
  const [value, setValue] = useState<EntryData>(view.consensus?.data ?? view.agreed);
  const save = useProjectMutation(() => saveConsensus(pid, form.id, rid, value), {
    invalidate: [extractionKeys.all(pid)],
    success: "Consensus saved. The extractions it reconciled are marked verified.",
  });
  const problems =
    save.error instanceof ApiError && typeof save.error.problem?.problems === "object"
      ? (save.error.problem.problems as Record<string, string>)
      : {};
  const names = view.entries.map((entry, index) => entry.extractor ?? `Extractor ${index + 1}`);
  return (
    <div className="grid gap-5">
      <div>
        <h2 className="text-lg font-medium">{view.title ?? "Untitled record"}</h2>
        <p className="text-sm text-muted-foreground">
          {view.label} · {view.entries.length} submitted extractions
          {view.consensus && ` · reconciled by ${view.consensus.resolved_by ?? "a former member"}`}
        </p>
      </div>

      {view.differences.length === 0 ? (
        <FormAlert tone="success">The extractions agree on every field.</FormAlert>
      ) : (
        <section aria-labelledby="differences" className="grid gap-2">
          <h3 id="differences" className="text-base font-medium">
            Where they differ ({view.differences.length})
          </h3>
          <ScrollRegion
            label="Values the extractors gave differently"
            className="rounded-lg border border-border"
          >
            <table className="w-full min-w-[32rem] text-sm">
              <caption className="sr-only">Values the extractors gave differently</caption>
              <thead className="bg-muted/50 text-left text-xs">
                <tr>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Field
                  </th>
                  {names.map((name, index) => (
                    <th key={index} scope="col" className="px-3 py-2 font-medium">
                      {name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {view.differences.map((difference) => (
                  <tr key={difference.path} className="border-t border-border align-top">
                    <th scope="row" className="px-3 py-2 text-left font-normal">
                      {difference.label}
                    </th>
                    {difference.values.map((given, index) => (
                      <td key={index} className="px-3 py-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span>{shown(given)}</span>
                          <Button
                            size="xs"
                            variant="outline"
                            aria-label={`Use ${names[index] ?? "this"}'s value for ${difference.label}`}
                            onClick={() => {
                              setValue((all) => withValue(all, difference.path, given ?? ""));
                            }}
                          >
                            Use
                          </Button>
                        </div>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollRegion>
        </section>
      )}

      <form
        aria-label="Consensus"
        className="grid gap-5"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate(undefined);
        }}
      >
        <h3 className="text-base font-medium">Consensus</h3>
        <EntryFields
          schema={schemaOf(form)}
          value={value}
          onChange={setValue}
          problems={problems}
          differs={new Set(view.differences.map((d) => d.path))}
        />
        {save.isError && <FormAlert>{errorMessage(save.error)}</FormAlert>}
        <div>
          <Button type="submit" disabled={save.isPending}>
            <CheckIcon aria-hidden="true" /> Save consensus
          </Button>
        </div>
      </form>
    </div>
  );
}

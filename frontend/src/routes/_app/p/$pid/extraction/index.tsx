import { useQuery } from "@tanstack/react-query";
import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import { CheckIcon, ClipboardListIcon } from "lucide-react";
import { useState } from "react";

import { ApiError, errorMessage } from "@/api/client";
import {
  extractionKeys,
  formsQuery,
  recordExtractionQuery,
  saveEntry,
  schemaOf,
  studiesQuery,
  type EntryData,
  type ExtractionForm,
  type StudyExtraction,
} from "@/api/extraction";
import { projectQuery } from "@/api/projects";
import { FormAlert } from "@/components/forms/FormAlert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EntryFields } from "@/features/extraction/EntryFields";
import { FormPicker } from "@/features/extraction/FormPicker";
import { useProjectMutation } from "@/features/projects/use-project-mutation";
import { extractionSearch } from "@/lib/search";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/p/$pid/extraction/")({
  validateSearch: extractionSearch,
  component: ExtractPage,
  staticData: { title: "Extract" },
});

const MINE: Record<StudyExtraction["mine"], string> = {
  none: "Not started",
  draft: "Draft",
  submitted: "Submitted",
  verified: "Reconciled",
};

function ExtractPage() {
  const { pid } = Route.useParams();
  const { form: chosen, study } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const { data: project } = useQuery(projectQuery(pid));
  const { data: forms, isPending } = useQuery(formsQuery(pid));
  const usable = (forms ?? []).filter((form) => form.published);
  const form = usable.find((f) => f.id === chosen) ?? usable.at(-1);

  if (isPending || !project)
    return <Skeleton className="h-64 w-full rounded-xl" aria-busy="true" />;
  if (!form) {
    return (
      <p className="grid justify-items-center gap-2 rounded-xl border border-dashed border-input p-10 text-center text-sm text-muted-foreground">
        <ClipboardListIcon className="size-6" aria-hidden="true" />
        No published form yet.
        {project.permissions.includes("edit_setup") ? (
          <Link to="/p/$pid/extraction/forms" params={{ pid }} className="underline">
            Build one under Forms
          </Link>
        ) : (
          " An owner or admin builds and publishes one."
        )}
      </p>
    );
  }
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
        <Studies pid={pid} form={form} selected={study} />
        <div className="min-w-0">
          {study ? (
            <Entry
              key={`${form.id}:${study}`}
              pid={pid}
              form={form}
              rid={study}
              canExtract={project.permissions.includes("screen")}
            />
          ) : (
            <p className="rounded-xl border border-dashed border-input p-6 text-center text-sm text-muted-foreground">
              Choose a study to extract its data.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function Studies({
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
  if (!studies || studies.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-input p-6 text-center text-sm text-muted-foreground">
        No studies yet. Studies appear once they are included at full text.
      </p>
    );
  }
  const done = studies.filter((s) => s.mine === "submitted" || s.mine === "verified").length;
  return (
    <nav aria-label="Studies" className="grid content-start gap-2">
      <p className="text-sm text-muted-foreground">
        You have extracted {done} of {studies.length}.
      </p>
      <ul className="grid gap-1">
        {studies.map((item) => (
          <li key={item.record_id}>
            <Link
              to="/p/$pid/extraction"
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
              <span className="line-clamp-1 text-xs text-muted-foreground">{item.title}</span>
              <span className="flex flex-wrap gap-1 pt-0.5">
                <Badge
                  variant={item.mine === "none" || item.mine === "draft" ? "secondary" : "default"}
                >
                  {MINE[item.mine]}
                </Badge>
                {item.consensus && <Badge variant="outline">Consensus</Badge>}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function Entry({
  pid,
  form,
  rid,
  canExtract,
}: {
  pid: string;
  form: ExtractionForm;
  rid: string;
  canExtract: boolean;
}) {
  const { data, error, isPending } = useQuery(recordExtractionQuery(pid, form.id, rid));
  if (isPending) return <Skeleton className="h-96 w-full rounded-xl" aria-busy="true" />;
  if (error) {
    return (
      <FormAlert>
        {error instanceof ApiError && error.status === 409
          ? "Data is extracted from studies included at full text; this one is not."
          : errorMessage(error)}
      </FormAlert>
    );
  }
  const mine = data.entries.find((entry) => entry.mine);
  return (
    <div className="grid gap-5">
      <div>
        <h2 className="text-lg font-medium">{data.title ?? "Untitled record"}</h2>
        <p className="text-sm text-muted-foreground">
          {data.label} · {form.name}, version {form.version}
        </p>
      </div>
      <MyEntry
        key={mine?.updated_at ?? "new"}
        pid={pid}
        form={form}
        rid={rid}
        initial={mine?.data ?? {}}
        status={mine?.status}
        canExtract={canExtract}
      />
      {data.consensus && (
        <section
          aria-label="Consensus"
          className="grid gap-2 rounded-xl border border-border bg-muted/30 p-4 text-sm"
        >
          <h3 className="font-medium">Consensus</h3>
          <p className="text-muted-foreground">
            Reconciled by {data.consensus.resolved_by ?? "a former member"}; this is what the
            review&apos;s export uses.
          </p>
        </section>
      )}
    </div>
  );
}

function MyEntry({
  pid,
  form,
  rid,
  initial,
  status,
  canExtract,
}: {
  pid: string;
  form: ExtractionForm;
  rid: string;
  initial: EntryData;
  status: string | undefined;
  canExtract: boolean;
}) {
  const [value, setValue] = useState<EntryData>(initial);
  const save = useProjectMutation(
    (next: "draft" | "submitted") => saveEntry(pid, form.id, rid, value, next),
    {
      invalidate: [extractionKeys.all(pid)],
      success: "Saved.",
    },
  );
  const problems =
    save.error instanceof ApiError && typeof save.error.problem?.problems === "object"
      ? (save.error.problem.problems as Record<string, string>)
      : {};
  return (
    <form
      className="grid gap-5"
      aria-label="Your extraction"
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate("submitted");
      }}
    >
      <div className="flex items-center gap-2">
        <h3 className="text-base font-medium">Your extraction</h3>
        {status && (
          <Badge variant={status === "draft" ? "secondary" : "default"}>
            {MINE[status as StudyExtraction["mine"]]}
          </Badge>
        )}
      </div>
      <EntryFields
        schema={schemaOf(form)}
        value={value}
        onChange={setValue}
        problems={problems}
        disabled={!canExtract}
      />
      {save.isError && <FormAlert>{errorMessage(save.error)}</FormAlert>}
      {canExtract && (
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={save.isPending}>
            <CheckIcon aria-hidden="true" /> Submit
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={save.isPending}
            onClick={() => {
              save.mutate("draft");
            }}
          >
            Save as draft
          </Button>
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        A draft can be partial; submitting checks every required field.
      </p>
    </form>
  );
}

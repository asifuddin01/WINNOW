import { useQuery } from "@tanstack/react-query";
import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import { CopyPlusIcon, LockIcon, PlusIcon, Trash2Icon } from "lucide-react";
import { useId, useState } from "react";

import {
  createForm,
  deleteForm,
  extractionKeys,
  formsQuery,
  newVersion,
  schemaOf,
  type ExtractionForm,
} from "@/api/extraction";
import { projectQuery } from "@/api/projects";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { EntryFields } from "@/features/extraction/EntryFields";
import { FormBuilder } from "@/features/extraction/FormBuilder";
import { ConfirmDialog } from "@/features/projects/ConfirmDialog";
import { useProjectMutation } from "@/features/projects/use-project-mutation";
import { extractionSearch } from "@/lib/search";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/p/$pid/extraction/forms")({
  validateSearch: extractionSearch,
  component: FormsPage,
  staticData: { title: "Forms" },
});

function FormsPage() {
  const { pid } = Route.useParams();
  const { form: chosen } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const { data: project } = useQuery(projectQuery(pid));
  const { data: forms, isPending } = useQuery(formsQuery(pid));
  const open = (id: string) => void navigate({ search: { form: id } });

  if (isPending || !project)
    return <Skeleton className="h-64 w-full rounded-xl" aria-busy="true" />;
  const canBuild = project.permissions.includes("edit_setup");
  const selected = forms?.find((form) => form.id === chosen);
  const families = new Map<string, ExtractionForm[]>();
  for (const form of forms ?? []) {
    families.set(form.family_id, [...(families.get(form.family_id) ?? []), form]);
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[18rem_1fr]">
      <div className="grid content-start gap-4">
        {canBuild && <NewForm pid={pid} onCreated={open} />}
        {families.size === 0 ? (
          <p className="text-sm text-muted-foreground">No forms yet.</p>
        ) : (
          <nav aria-label="Forms and their versions" className="grid gap-3">
            {[...families.values()].map((versions) => (
              <div key={versions[0]?.family_id} className="grid gap-1">
                <p className="text-sm font-medium">{versions.at(-1)?.name}</p>
                <ul className="flex flex-wrap gap-1">
                  {versions.map((form) => (
                    <li key={form.id}>
                      <Link
                        to="/p/$pid/extraction/forms"
                        params={{ pid }}
                        search={{ form: form.id }}
                        aria-current={form.id === chosen ? "page" : undefined}
                        className={cn(
                          "inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-0.5 text-xs hover:bg-muted",
                          "focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
                          form.id === chosen && "border-primary bg-primary/10 font-medium",
                        )}
                      >
                        Version {form.version}
                        {form.published ? (
                          <LockIcon className="size-3" aria-label="published" />
                        ) : (
                          <span className="text-muted-foreground">(draft)</span>
                        )}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </nav>
        )}
      </div>
      <div className="min-w-0">
        {selected ? (
          selected.published || !canBuild ? (
            <Preview
              key={selected.id}
              pid={pid}
              form={selected}
              canBuild={canBuild}
              onVersion={open}
            />
          ) : (
            <div className="grid gap-4">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-medium">
                  {selected.name}, version {selected.version}
                </h2>
                <Badge variant="secondary">Draft</Badge>
                <DeleteDraft
                  pid={pid}
                  form={selected}
                  onDeleted={() => void navigate({ search: {} })}
                />
              </div>
              <FormBuilder key={selected.id} pid={pid} form={selected} />
            </div>
          )
        ) : (
          <p className="rounded-xl border border-dashed border-input p-6 text-center text-sm text-muted-foreground">
            {canBuild
              ? "Create a form, or choose a version to edit or read."
              : "Choose a version to read it. Owners and admins build forms."}
          </p>
        )}
      </div>
    </div>
  );
}

function NewForm({ pid, onCreated }: { pid: string; onCreated: (id: string) => void }) {
  const id = useId();
  const [name, setName] = useState("");
  const [dual, setDual] = useState(false);
  const create = useProjectMutation(() => createForm(pid, name.trim(), dual), {
    invalidate: [extractionKeys.forms(pid)],
    success: "Form created as a draft.",
  });
  return (
    <form
      className="grid gap-3 rounded-xl border border-border bg-card p-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (!name.trim()) return;
        create.mutate(undefined, {
          onSuccess: (form) => {
            setName("");
            onCreated(form.id);
          },
        });
      }}
    >
      <div className="grid gap-1.5">
        <Label htmlFor={`${id}-name`}>New form</Label>
        <Input
          id={`${id}-name`}
          value={name}
          maxLength={200}
          placeholder="Trial characteristics"
          onChange={(event) => {
            setName(event.target.value);
          }}
        />
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          className="size-4 accent-primary"
          checked={dual}
          onChange={(event) => {
            setDual(event.target.checked);
          }}
        />
        Two extractors per study
      </label>
      <div>
        <Button type="submit" size="sm" disabled={!name.trim() || create.isPending}>
          <PlusIcon aria-hidden="true" /> Create
        </Button>
      </div>
    </form>
  );
}

function Preview({
  pid,
  form,
  canBuild,
  onVersion,
}: {
  pid: string;
  form: ExtractionForm;
  canBuild: boolean;
  onVersion: (id: string) => void;
}) {
  const next = useProjectMutation(() => newVersion(pid, form.id), {
    invalidate: [extractionKeys.forms(pid)],
    success: "A new draft version, copied from this one.",
  });
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-medium">
          {form.name}, version {form.version}
        </h2>
        <Badge variant={form.published ? "default" : "secondary"}>
          {form.published ? "Published" : "Draft"}
        </Badge>
        {form.dual && <Badge variant="outline">Two extractors</Badge>}
        {canBuild && form.published && form.latest && (
          <Button
            size="sm"
            variant="outline"
            className="ml-auto"
            disabled={next.isPending}
            onClick={() => {
              next.mutate(undefined, {
                onSuccess: (created) => {
                  onVersion(created.id);
                },
              });
            }}
          >
            <CopyPlusIcon aria-hidden="true" /> Start version {form.version + 1}
          </Button>
        )}
      </div>
      {form.published && (
        <p className="text-sm text-muted-foreground">
          Published and locked: {form.entries}{" "}
          {form.entries === 1 ? "extraction uses" : "extractions use"} it.
        </p>
      )}
      <div className="rounded-xl border border-border bg-card p-4">
        <EntryFields schema={schemaOf(form)} value={{}} onChange={() => undefined} disabled />
      </div>
    </div>
  );
}

function DeleteDraft({
  pid,
  form,
  onDeleted,
}: {
  pid: string;
  form: ExtractionForm;
  onDeleted: () => void;
}) {
  const remove = useProjectMutation(() => deleteForm(pid, form.id), {
    invalidate: [extractionKeys.forms(pid)],
    success: "Draft deleted.",
  });
  return (
    <ConfirmDialog
      trigger={
        <Button
          size="sm"
          variant="ghost"
          className="ml-auto text-destructive"
          disabled={remove.isPending}
        >
          <Trash2Icon aria-hidden="true" /> Delete this draft
        </Button>
      }
      title={`Delete version ${form.version} of ${form.name}?`}
      description="The draft and its fields are removed. Published versions are not touched."
      confirmLabel="Delete draft"
      destructive
      onConfirm={() => {
        remove.mutate(undefined, { onSuccess: onDeleted });
      }}
    />
  );
}

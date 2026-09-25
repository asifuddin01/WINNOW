import {
  ArrowDownIcon,
  ArrowUpIcon,
  GripVerticalIcon,
  PlusIcon,
  SendIcon,
  Trash2Icon,
} from "lucide-react";
import { useId, useState } from "react";

import { ApiError, errorMessage } from "@/api/client";
import {
  extractionKeys,
  publishForm,
  schemaOf,
  updateForm,
  type ExtractionForm,
  type FieldDef,
  type FieldType,
} from "@/api/extraction";
import { FormAlert } from "@/components/forms/FormAlert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useProjectMutation } from "@/features/projects/use-project-mutation";
import { FIELD_TYPES, SCALAR_TYPES, keyFrom } from "@/features/extraction/fields";

/** A field while it is being edited: `keyEdited` stops the key following the label. */
interface Draft extends Omit<FieldDef, "columns"> {
  uid: number;
  keyEdited: boolean;
  columns?: Draft[];
}

let next = 0;
const uid = () => (next += 1);

const toDraft = (field: FieldDef): Draft => ({
  ...field,
  uid: uid(),
  keyEdited: true,
  columns: field.columns?.map(toDraft),
});

/** The field as the server takes it: only the settings its type has, nothing blank. */
const toField = (draft: Draft): FieldDef => {
  const { type } = draft;
  const clean: FieldDef = { key: draft.key.trim(), label: draft.label.trim(), type };
  if (draft.help?.trim()) clean.help = draft.help.trim();
  if (draft.required && type !== "section") clean.required = true;
  if (type === "select" || type === "multi_select") {
    clean.options = (draft.options ?? []).map((option) => option.trim()).filter(Boolean);
  }
  if (type === "number") {
    if (draft.unit?.trim()) clean.unit = draft.unit.trim();
    if (draft.integer) clean.integer = true;
    if (draft.minimum !== undefined && !Number.isNaN(draft.minimum)) clean.minimum = draft.minimum;
    if (draft.maximum !== undefined && !Number.isNaN(draft.maximum)) clean.maximum = draft.maximum;
  }
  if (type === "table") {
    clean.columns = (draft.columns ?? []).map(toField);
    if (draft.min_rows) clean.min_rows = draft.min_rows;
    if (draft.max_rows !== undefined) clean.max_rows = draft.max_rows;
  }
  return clean;
};

function blank(type: FieldType, taken: string[]): Draft {
  const label = FIELD_TYPES.find((t) => t.value === type)?.label ?? "Field";
  const field: Draft = { uid: uid(), keyEdited: false, key: keyFrom(label, taken), label, type };
  if (type === "select" || type === "multi_select") field.options = ["Option 1", "Option 2"];
  if (type === "table") field.columns = [blank("short_text", [])];
  return field;
}

/** Edit a draft version; publishing locks it (guide 8.12). */
export function FormBuilder({ pid, form }: { pid: string; form: ExtractionForm }) {
  const id = useId();
  const [name, setName] = useState(form.name);
  const [dual, setDual] = useState(form.dual);
  const [fields, setFields] = useState<Draft[]>(() => schemaOf(form).fields.map(toDraft));
  const [dragged, setDragged] = useState<number | null>(null);
  const invalidate = [extractionKeys.forms(pid)];
  const body = () => ({ name, dual, schema: { fields: fields.map(toField) } });
  const save = useProjectMutation(() => updateForm(pid, form.id, body()), {
    invalidate,
    success: "Draft saved.",
  });
  const publish = useProjectMutation(
    async () => {
      await updateForm(pid, form.id, body());
      return publishForm(pid, form.id);
    },
    { invalidate, success: "Published. Reviewers can extract with it now." },
  );
  const failed = save.error ?? publish.error;
  const problems =
    failed instanceof ApiError && Array.isArray(failed.problem?.problems)
      ? (failed.problem.problems as string[])
      : null;

  const move = (from: number, to: number) => {
    if (to < 0 || to >= fields.length || from === to) return;
    setFields((all) => {
      const copy = [...all];
      const [item] = copy.splice(from, 1);
      if (item) copy.splice(to, 0, item);
      return copy;
    });
  };
  const add = (type: FieldType) => {
    setFields((all) => [
      ...all,
      blank(
        type,
        all.map((f) => f.key),
      ),
    ]);
  };

  return (
    <div className="grid gap-5">
      <div className="grid gap-4 rounded-xl border border-border bg-card p-4 sm:grid-cols-[1fr_auto] sm:items-end">
        <div className="grid gap-1.5">
          <Label htmlFor={`${id}-name`}>Form name</Label>
          <Input
            id={`${id}-name`}
            value={name}
            maxLength={200}
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
          Two people extract each study, then reconcile
        </label>
      </div>

      {fields.length === 0 && (
        <p className="rounded-xl border border-dashed border-input p-6 text-center text-sm text-muted-foreground">
          No fields yet. Add the first one below.
        </p>
      )}
      <ol className="grid gap-3" aria-label="Fields">
        {fields.map((field, index) => (
          <li
            key={field.uid}
            draggable
            onDragStart={() => {
              setDragged(index);
            }}
            onDragOver={(event) => {
              event.preventDefault();
            }}
            onDrop={() => {
              if (dragged !== null) move(dragged, index);
              setDragged(null);
            }}
            className="rounded-xl border border-border bg-card p-4"
          >
            <FieldEditor
              field={field}
              taken={fields.filter((f) => f.uid !== field.uid).map((f) => f.key)}
              onChange={(changed) => {
                setFields((all) => all.map((f) => (f.uid === field.uid ? changed : f)));
              }}
              tools={
                <div className="flex items-center gap-1">
                  <GripVerticalIcon
                    className="size-4 cursor-grab text-muted-foreground"
                    aria-hidden="true"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Move ${field.label} up`}
                    disabled={index === 0}
                    onClick={() => {
                      move(index, index - 1);
                    }}
                  >
                    <ArrowUpIcon aria-hidden="true" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Move ${field.label} down`}
                    disabled={index === fields.length - 1}
                    onClick={() => {
                      move(index, index + 1);
                    }}
                  >
                    <ArrowDownIcon aria-hidden="true" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Remove ${field.label}`}
                    onClick={() => {
                      setFields((all) => all.filter((f) => f.uid !== field.uid));
                    }}
                  >
                    <Trash2Icon aria-hidden="true" />
                  </Button>
                </div>
              }
            />
          </li>
        ))}
      </ol>

      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Add a field">
        <span className="text-sm text-muted-foreground">Add:</span>
        {FIELD_TYPES.map((type) => (
          <Button
            key={type.value}
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              add(type.value);
            }}
          >
            <PlusIcon aria-hidden="true" /> {type.label}
          </Button>
        ))}
      </div>

      {failed !== null && (
        <FormAlert>
          {problems ? (
            <>
              The form has problems:
              <ul className="mt-1 list-disc pl-5">
                {problems.map((problem) => (
                  <li key={problem}>{problem}</li>
                ))}
              </ul>
            </>
          ) : (
            errorMessage(failed)
          )}
        </FormAlert>
      )}
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          disabled={save.isPending || publish.isPending}
          onClick={() => {
            publish.reset();
            save.mutate(undefined);
          }}
        >
          Save draft
        </Button>
        <Button
          disabled={save.isPending || publish.isPending}
          onClick={() => {
            save.reset();
            publish.mutate(undefined);
          }}
        >
          <SendIcon aria-hidden="true" /> Publish version {form.version}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        A published version is locked, so data is always read with the form it was extracted on. To
        change it later, start the next version.
      </p>
    </div>
  );
}

function FieldEditor({
  field,
  taken,
  onChange,
  tools,
  inTable = false,
}: {
  field: Draft;
  taken: string[];
  onChange: (field: Draft) => void;
  tools: React.ReactNode;
  inTable?: boolean;
}) {
  const id = useId();
  const set = (changes: Partial<Draft>) => {
    onChange({ ...field, ...changes });
  };
  const types = inTable ? FIELD_TYPES.filter((t) => SCALAR_TYPES.includes(t.value)) : FIELD_TYPES;
  const number = (text: string) => (text.trim() === "" ? undefined : Number(text));
  return (
    <fieldset className="grid gap-3">
      <legend className="sr-only">{field.label}</legend>
      <div className="flex flex-wrap items-end gap-3">
        <div className="grid min-w-48 flex-1 gap-1">
          <Label htmlFor={`${id}-label`}>Label</Label>
          <Input
            id={`${id}-label`}
            value={field.label}
            maxLength={300}
            onChange={(event) => {
              const label = event.target.value;
              set(field.keyEdited ? { label } : { label, key: keyFrom(label, taken) });
            }}
          />
        </div>
        <div className="grid w-44 gap-1">
          <Label htmlFor={`${id}-type`}>Type</Label>
          <select
            id={`${id}-type`}
            value={field.type}
            onChange={(event) => {
              const type = event.target.value as FieldType;
              const fresh = blank(type, taken);
              set({ type, options: fresh.options, columns: fresh.columns });
            }}
            className="h-9 rounded-md border border-input bg-transparent px-2.5 text-sm shadow-xs focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            {types.map((type) => (
              <option key={type.value} value={type.value}>
                {type.label}
              </option>
            ))}
          </select>
        </div>
        {tools}
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <div className="grid w-52 gap-1">
          <Label htmlFor={`${id}-key`}>Column name in exports</Label>
          <Input
            id={`${id}-key`}
            value={field.key}
            maxLength={40}
            className="font-mono text-sm"
            onChange={(event) => {
              set({ key: event.target.value, keyEdited: true });
            }}
          />
        </div>
        {field.type !== "section" && (
          <label className="flex items-center gap-2 pb-2 text-sm">
            <input
              type="checkbox"
              className="size-4 accent-primary"
              checked={field.required ?? false}
              onChange={(event) => {
                set({ required: event.target.checked });
              }}
            />
            Required
          </label>
        )}
      </div>
      {!inTable && (
        <div className="grid gap-1">
          <Label htmlFor={`${id}-help`}>Help text</Label>
          <Input
            id={`${id}-help`}
            value={field.help ?? ""}
            maxLength={2000}
            onChange={(event) => {
              set({ help: event.target.value });
            }}
          />
        </div>
      )}
      {(field.type === "select" || field.type === "multi_select") && (
        <div className="grid gap-1">
          <Label htmlFor={`${id}-options`}>Options, one per line</Label>
          <Textarea
            id={`${id}-options`}
            rows={3}
            value={(field.options ?? []).join("\n")}
            onChange={(event) => {
              set({ options: event.target.value.split("\n") });
            }}
          />
        </div>
      )}
      {field.type === "number" && (
        <div className="flex flex-wrap items-end gap-3">
          <div className="grid w-32 gap-1">
            <Label htmlFor={`${id}-unit`}>Unit</Label>
            <Input
              id={`${id}-unit`}
              value={field.unit ?? ""}
              maxLength={50}
              onChange={(event) => {
                set({ unit: event.target.value });
              }}
            />
          </div>
          <div className="grid w-28 gap-1">
            <Label htmlFor={`${id}-min`}>Minimum</Label>
            <Input
              id={`${id}-min`}
              inputMode="decimal"
              value={field.minimum ?? ""}
              onChange={(event) => {
                set({ minimum: number(event.target.value) });
              }}
            />
          </div>
          <div className="grid w-28 gap-1">
            <Label htmlFor={`${id}-max`}>Maximum</Label>
            <Input
              id={`${id}-max`}
              inputMode="decimal"
              value={field.maximum ?? ""}
              onChange={(event) => {
                set({ maximum: number(event.target.value) });
              }}
            />
          </div>
          <label className="flex items-center gap-2 pb-2 text-sm">
            <input
              type="checkbox"
              className="size-4 accent-primary"
              checked={field.integer ?? false}
              onChange={(event) => {
                set({ integer: event.target.checked });
              }}
            />
            Whole numbers only
          </label>
        </div>
      )}
      {field.type === "table" && (
        <div className="grid gap-3 rounded-lg border border-border bg-muted/30 p-3">
          <p className="text-sm font-medium">Columns of {field.label}</p>
          {(field.columns ?? []).map((column, _index, all) => (
            <div key={column.uid} className="rounded-lg border border-border bg-card p-3">
              <FieldEditor
                inTable
                field={column}
                taken={all.filter((c) => c.uid !== column.uid).map((c) => c.key)}
                onChange={(changed) => {
                  set({ columns: all.map((c) => (c.uid === column.uid ? changed : c)) });
                }}
                tools={
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Remove column ${column.label}`}
                    disabled={all.length === 1}
                    onClick={() => {
                      set({ columns: all.filter((c) => c.uid !== column.uid) });
                    }}
                  >
                    <Trash2Icon aria-hidden="true" />
                  </Button>
                }
              />
            </div>
          ))}
          <div className="flex flex-wrap items-end gap-3">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                set({
                  columns: [
                    ...(field.columns ?? []),
                    blank(
                      "short_text",
                      (field.columns ?? []).map((c) => c.key),
                    ),
                  ],
                });
              }}
            >
              <PlusIcon aria-hidden="true" /> Add a column
            </Button>
            <div className="grid w-28 gap-1">
              <Label htmlFor={`${id}-min-rows`}>Fewest rows</Label>
              <Input
                id={`${id}-min-rows`}
                inputMode="numeric"
                value={field.min_rows ?? ""}
                onChange={(event) => {
                  set({ min_rows: number(event.target.value) });
                }}
              />
            </div>
            <div className="grid w-28 gap-1">
              <Label htmlFor={`${id}-max-rows`}>Most rows</Label>
              <Input
                id={`${id}-max-rows`}
                inputMode="numeric"
                value={field.max_rows ?? ""}
                onChange={(event) => {
                  set({ max_rows: number(event.target.value) });
                }}
              />
            </div>
          </div>
        </div>
      )}
    </fieldset>
  );
}

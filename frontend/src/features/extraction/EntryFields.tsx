import { PlusIcon, Trash2Icon, TriangleAlertIcon } from "lucide-react";
import { useId } from "react";

import type { EntryData, FieldDef, FormSchema, Row } from "@/api/extraction";
import { ScrollRegion } from "@/components/layout/ScrollRegion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

const YES_NO_UNCLEAR = [
  { value: "yes", label: "Yes" },
  { value: "no", label: "No" },
  { value: "unclear", label: "Unclear" },
];

interface Props {
  schema: FormSchema;
  value: EntryData;
  onChange: (next: EntryData) => void;
  /** The server's problems, keyed by path ("n", "arms[2].mean"). */
  problems?: Record<string, string>;
  /** Paths where extractors disagree, marked for the consensus. */
  differs?: Set<string>;
  disabled?: boolean;
}

/** A form's fields, filled in: text, numbers with units, choices, dates and tables. */
export function EntryFields({ schema, value, onChange, problems = {}, differs, disabled }: Props) {
  return (
    <div className="grid gap-5">
      {schema.fields.map((field) =>
        field.type === "section" ? (
          <div key={field.key} className="border-b border-border pt-2 pb-1">
            <h3 className="text-base font-semibold">{field.label}</h3>
            {field.help && <p className="text-sm text-muted-foreground">{field.help}</p>}
          </div>
        ) : field.type === "table" ? (
          <TableField
            key={field.key}
            field={field}
            rows={(value[field.key] as Row[] | undefined) ?? []}
            problems={problems}
            differs={differs}
            disabled={disabled}
            onChange={(rows) => {
              onChange({ ...value, [field.key]: rows });
            }}
          />
        ) : (
          <ScalarField
            key={field.key}
            field={field}
            path={field.key}
            value={value[field.key]}
            problem={problems[field.key]}
            differs={differs?.has(field.key)}
            disabled={disabled}
            onChange={(next) => {
              onChange({ ...value, [field.key]: next });
            }}
          />
        ),
      )}
    </div>
  );
}

function Differs() {
  return (
    <span className="ml-2 inline-flex items-center gap-1 rounded-full border border-maybe/50 bg-maybe/10 px-2 py-0.5 text-xs font-medium text-foreground">
      <TriangleAlertIcon className="size-3 text-maybe" aria-hidden="true" /> Extractors differ
    </span>
  );
}

function ScalarField({
  field,
  path,
  value,
  problem,
  differs,
  disabled,
  onChange,
  compact = false,
}: {
  field: FieldDef;
  path: string;
  value: unknown;
  problem?: string;
  differs?: boolean;
  disabled?: boolean;
  onChange: (next: unknown) => void;
  compact?: boolean;
}) {
  const id = useId();
  const described = [field.help && `${id}-help`, problem && `${id}-problem`]
    .filter(Boolean)
    .join(" ");
  const common = {
    "aria-invalid": problem ? true : undefined,
    "aria-describedby": described || undefined,
    disabled,
  };
  const label = (
    <>
      {field.label}
      {field.required && <span aria-hidden="true"> *</span>}
      {field.required && <span className="sr-only"> (required)</span>}
      {field.unit && <span className="font-normal text-muted-foreground"> ({field.unit})</span>}
      {differs && <Differs />}
    </>
  );
  const text = typeof value === "string" || typeof value === "number" ? String(value) : "";

  let control: React.ReactNode;
  if (field.type === "long_text") {
    control = (
      <Textarea
        id={id}
        rows={compact ? 1 : 3}
        value={text}
        onChange={(event) => {
          onChange(event.target.value);
        }}
        {...common}
      />
    );
  } else if (field.type === "select") {
    control = (
      <select
        id={id}
        value={text}
        onChange={(event) => {
          onChange(event.target.value);
        }}
        className="h-9 w-full rounded-md border border-input bg-transparent px-2.5 text-sm shadow-xs focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none disabled:opacity-50"
        {...common}
      >
        <option value="">Not given</option>
        {(field.options ?? []).map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    );
  } else if (field.type === "multi_select" || field.type === "yes_no_unclear") {
    const many = field.type === "multi_select";
    const chosen = many ? ((value as string[] | undefined) ?? []) : [text];
    const options = many
      ? (field.options ?? []).map((option) => ({ value: option, label: option }))
      : YES_NO_UNCLEAR;
    return (
      <fieldset
        className="grid gap-1.5"
        aria-describedby={described || undefined}
        disabled={disabled}
      >
        <legend className={cn("mb-1 text-sm font-medium", compact && "sr-only")}>{label}</legend>
        <div className="flex flex-wrap gap-1.5">
          {options.map((option) => (
            <label
              key={option.value}
              className="flex cursor-pointer items-center gap-1.5 rounded-full border border-border px-3 py-1 text-sm has-checked:border-primary has-checked:bg-primary/10 has-focus-visible:ring-3 has-focus-visible:ring-ring/50"
            >
              <input
                type={many ? "checkbox" : "radio"}
                name={`${id}-choice`}
                checked={chosen.includes(option.value)}
                className="sr-only"
                onChange={(event) => {
                  if (!many) {
                    onChange(option.value);
                    return;
                  }
                  onChange(
                    event.target.checked
                      ? [...chosen, option.value]
                      : chosen.filter((item) => item !== option.value),
                  );
                }}
              />
              {option.label}
            </label>
          ))}
          {!many && text && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                onChange("");
              }}
            >
              Clear
            </Button>
          )}
        </div>
        <Hints id={id} field={field} problem={problem} />
      </fieldset>
    );
  } else {
    control = (
      <Input
        id={id}
        type={field.type === "date" ? "date" : "text"}
        inputMode={field.type === "number" ? "decimal" : undefined}
        value={text}
        onChange={(event) => {
          onChange(event.target.value);
        }}
        {...common}
      />
    );
  }
  return (
    <div className="grid gap-1.5" data-path={path}>
      <label htmlFor={id} className={cn("text-sm font-medium", compact && "sr-only")}>
        {label}
      </label>
      {control}
      <Hints id={id} field={field} problem={problem} />
    </div>
  );
}

function Hints({ id, field, problem }: { id: string; field: FieldDef; problem?: string }) {
  return (
    <>
      {field.help && (
        <p id={`${id}-help`} className="text-xs text-muted-foreground">
          {field.help}
        </p>
      )}
      {problem && (
        <p id={`${id}-problem`} className="text-sm text-destructive">
          {problem}
        </p>
      )}
    </>
  );
}

function TableField({
  field,
  rows,
  problems,
  differs,
  disabled,
  onChange,
}: {
  field: FieldDef;
  rows: Row[];
  problems: Record<string, string>;
  differs?: Set<string>;
  disabled?: boolean;
  onChange: (rows: Row[]) => void;
}) {
  const columns = field.columns ?? [];
  const full = field.max_rows !== undefined && rows.length >= field.max_rows;
  return (
    // Each control is disabled on its own rather than the fieldset, whose disabling would
    // also take the table's scroll area out of reach (axe counts it as disabled too).
    <fieldset className="grid gap-2">
      <legend className="mb-1 text-sm font-medium">
        {field.label}
        {field.required && <span className="sr-only"> (required)</span>}
      </legend>
      {field.help && <p className="text-xs text-muted-foreground">{field.help}</p>}
      <ScrollRegion label={field.label} className="rounded-lg border border-border">
        <table className="w-full min-w-[32rem] text-sm">
          <caption className="sr-only">{field.label}</caption>
          <thead className="bg-muted/50 text-left text-xs">
            <tr>
              <th scope="col" className="w-10 px-2 py-2 font-medium">
                Row
              </th>
              {columns.map((column) => (
                <th key={column.key} scope="col" className="px-2 py-2 font-medium">
                  {column.label}
                  {column.unit && <span className="text-muted-foreground"> ({column.unit})</span>}
                </th>
              ))}
              <th scope="col" className="w-10 px-2 py-2">
                <span className="sr-only">Remove</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index} className="border-t border-border align-top">
                <th scope="row" className="px-2 py-2 text-left font-normal tabular-nums">
                  {index + 1}
                </th>
                {columns.map((column) => {
                  const path = `${field.key}[${index + 1}].${column.key}`;
                  return (
                    <td key={column.key} className="px-2 py-1.5">
                      <ScalarField
                        compact
                        field={{ ...column, label: `${column.label}, row ${index + 1}` }}
                        path={path}
                        value={row[column.key]}
                        problem={problems[path]}
                        differs={differs?.has(path)}
                        disabled={disabled}
                        onChange={(next) => {
                          onChange(
                            rows.map((r, i) => (i === index ? { ...r, [column.key]: next } : r)),
                          );
                        }}
                      />
                    </td>
                  );
                })}
                <td className="px-2 py-1.5">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    disabled={disabled}
                    aria-label={`Remove row ${index + 1} of ${field.label}`}
                    onClick={() => {
                      onChange(rows.filter((_, i) => i !== index));
                    }}
                  >
                    <Trash2Icon aria-hidden="true" />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </ScrollRegion>
      {problems[field.key] && <p className="text-sm text-destructive">{problems[field.key]}</p>}
      <div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={(disabled ?? false) || full}
          onClick={() => {
            onChange([...rows, {}]);
          }}
        >
          <PlusIcon aria-hidden="true" /> Add a row to {field.label}
        </Button>
      </div>
    </fieldset>
  );
}

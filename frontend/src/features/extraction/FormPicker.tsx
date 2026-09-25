import { useId } from "react";

import type { ExtractionForm } from "@/api/extraction";
import { Label } from "@/components/ui/label";

/** Which form version to work with; the newest is listed last. */
export function FormPicker({
  forms,
  value,
  onChange,
  label = "Form",
}: {
  forms: ExtractionForm[];
  value: string;
  onChange: (id: string) => void;
  label?: string;
}) {
  const id = useId();
  return (
    <div className="grid w-full max-w-sm gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <select
        id={id}
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
        className="h-9 rounded-md border border-input bg-transparent px-2.5 text-sm shadow-xs focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        {forms.map((form) => (
          <option key={form.id} value={form.id}>
            {form.name}, version {form.version}
            {form.dual ? " (two extractors)" : ""}
          </option>
        ))}
      </select>
    </div>
  );
}

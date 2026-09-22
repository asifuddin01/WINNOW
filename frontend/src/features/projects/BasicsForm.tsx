import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, useWatch } from "react-hook-form";

import { FormAlert } from "@/components/forms/FormAlert";
import { SelectField } from "@/components/forms/SelectField";
import { TextareaField } from "@/components/forms/TextareaField";
import { TextField } from "@/components/forms/TextField";
import { Button } from "@/components/ui/button";
import { basicsSchema, type BasicsValues } from "@/features/projects/schemas";
import { REVIEW_TYPES } from "@/features/projects/wording";

const REVIEW_TYPE_OPTIONS = Object.entries(REVIEW_TYPES).map(([value, label]) => ({
  value: value as BasicsValues["review_type"],
  label,
}));

interface BasicsFormProps {
  defaultValues: BasicsValues;
  submitLabel: string;
  pending: boolean;
  problem?: string | null;
  onSubmit: (values: BasicsValues) => void;
  footer?: React.ReactNode;
}

/** Title, type, question and PICO: step one of the wizard, and the settings page. */
export function BasicsForm({
  defaultValues,
  submitLabel,
  pending,
  problem,
  onSubmit,
  footer,
}: BasicsFormProps) {
  const form = useForm<BasicsValues>({ resolver: zodResolver(basicsSchema), defaultValues });
  const errors = form.formState.errors;
  const reviewType = useWatch({ control: form.control, name: "review_type" });

  return (
    <form
      className="grid gap-5"
      noValidate
      onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}
    >
      {problem && <FormAlert>{problem}</FormAlert>}
      <TextField
        label="Title"
        autoComplete="off"
        error={errors.title?.message}
        {...form.register("title")}
      />
      <SelectField
        label="Type of review"
        value={reviewType}
        options={REVIEW_TYPE_OPTIONS}
        onChange={(value) => {
          form.setValue("review_type", value, { shouldDirty: true });
        }}
      />
      <TextareaField
        label="Research question"
        rows={2}
        hint="Optional. The question this review sets out to answer."
        error={errors.research_question?.message}
        {...form.register("research_question")}
      />
      <TextareaField
        label="Description"
        rows={2}
        hint="Optional. Notes for your team."
        error={errors.description?.message}
        {...form.register("description")}
      />
      <fieldset className="grid gap-3 rounded-lg border border-border p-4 sm:grid-cols-2">
        <legend className="px-1 text-sm font-medium">PICO (optional)</legend>
        <TextField label="Population" {...form.register("population")} />
        <TextField label="Intervention" {...form.register("intervention")} />
        <TextField label="Comparator" {...form.register("comparator")} />
        <TextField label="Outcome" {...form.register("outcome")} />
      </fieldset>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={pending}>
          {pending ? "Saving…" : submitLabel}
        </Button>
        {footer}
      </div>
    </form>
  );
}

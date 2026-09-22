import { useId, type ComponentProps, type ReactNode } from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

interface TextFieldProps extends ComponentProps<"input"> {
  label: string;
  error?: string | undefined;
  hint?: ReactNode;
  /** Rendered inside the field, after the input (e.g. a show-password toggle). */
  trailing?: ReactNode;
}

/** Label, input, hint and error, wired together for screen readers (guide 14). */
export function TextField({ label, error, hint, trailing, className, ...input }: TextFieldProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <div className="relative">
        <Input
          id={id}
          aria-invalid={error ? true : undefined}
          aria-describedby={[hintId, errorId].filter(Boolean).join(" ") || undefined}
          className={cn("h-10", trailing && "pr-11", className)}
          {...input}
        />
        {trailing && <div className="absolute inset-y-0 right-1 flex items-center">{trailing}</div>}
      </div>
      {hint && (
        <p id={hintId} className="text-xs text-muted-foreground">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="text-xs font-medium text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

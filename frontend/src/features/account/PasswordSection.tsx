import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { changePassword, isApiError } from "@/api/auth";
import { errorMessage } from "@/api/client";
import { FormAlert } from "@/components/forms/FormAlert";
import { PasswordField } from "@/components/forms/PasswordField";
import { Button } from "@/components/ui/button";
import { Section } from "@/features/account/Section";
import {
  PASSWORD_HINT,
  changePasswordSchema,
  type ChangePasswordValues,
} from "@/features/auth/schemas";

export function PasswordSection() {
  const queryClient = useQueryClient();
  const [problem, setProblem] = useState<string | null>(null);
  const form = useForm<ChangePasswordValues>({
    resolver: zodResolver(changePasswordSchema),
    defaultValues: { current: "", next: "" },
  });
  const { errors, isSubmitting } = form.formState;

  const onSubmit = form.handleSubmit(async ({ current, next }) => {
    setProblem(null);
    try {
      await changePassword(queryClient, { current_password: current, new_password: next });
      form.reset();
      toast.success("Password changed. Other devices were signed out.");
    } catch (error) {
      if (isApiError(error, "incorrect_password"))
        form.setError("current", { message: error.message });
      else if (isApiError(error, "weak_password"))
        form.setError("next", { message: error.message });
      else setProblem(errorMessage(error));
    }
  });

  return (
    <Section title="Password" description="Changing it signs out every other device.">
      <form noValidate onSubmit={(event) => void onSubmit(event)} className="grid max-w-sm gap-4">
        {problem && <FormAlert>{problem}</FormAlert>}
        <PasswordField
          label="Current password"
          autoComplete="current-password"
          error={errors.current?.message}
          {...form.register("current")}
        />
        <PasswordField
          label="New password"
          autoComplete="new-password"
          hint={PASSWORD_HINT}
          error={errors.next?.message}
          {...form.register("next")}
        />
        <Button type="submit" className="justify-self-start" disabled={isSubmitting}>
          {isSubmitting ? "Saving…" : "Change password"}
        </Button>
      </form>
    </Section>
  );
}

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { createFileRoute, redirect, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { isApiError, loadAuthOptions, setUpAdmin } from "@/api/auth";
import { errorMessage } from "@/api/client";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { FormAlert } from "@/components/forms/FormAlert";
import { PasswordField } from "@/components/forms/PasswordField";
import { TextField } from "@/components/forms/TextField";
import { Button } from "@/components/ui/button";
import { PASSWORD_HINT, registerSchema, type RegisterValues } from "@/features/auth/schemas";

export const Route = createFileRoute("/setup")({
  beforeLoad: async ({ context }) => {
    const options = await loadAuthOptions(context.queryClient);
    if (!options.needs_setup) redirect({ to: "/login", throw: true });
  },
  component: Setup,
  staticData: { title: "Set up Winnow" },
});

/** Single-user mode's first run (guide 8.1): create the one administrator account. */
function Setup() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [problem, setProblem] = useState<string | null>(null);
  const form = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { name: "", email: "", password: "" },
  });
  const { errors, isSubmitting } = form.formState;

  const onSubmit = form.handleSubmit(async (values) => {
    setProblem(null);
    try {
      await setUpAdmin(queryClient, values);
      await navigate({ to: "/", replace: true });
    } catch (error) {
      if (isApiError(error, "weak_password")) form.setError("password", { message: error.message });
      else setProblem(errorMessage(error));
    }
  });

  return (
    <AuthLayout
      title="Set up Winnow"
      description="This instance runs for one person. Create your account to begin; no email confirmation needed."
    >
      <form noValidate onSubmit={(event) => void onSubmit(event)} className="grid gap-4">
        {problem && <FormAlert>{problem}</FormAlert>}
        <TextField
          label="Name"
          autoComplete="name"
          error={errors.name?.message}
          {...form.register("name")}
        />
        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          error={errors.email?.message}
          {...form.register("email")}
        />
        <PasswordField
          label="Password"
          autoComplete="new-password"
          hint={PASSWORD_HINT}
          error={errors.password?.message}
          {...form.register("password")}
        />
        <Button type="submit" size="lg" className="mt-1 h-10" disabled={isSubmitting}>
          {isSubmitting ? "Creating account…" : "Create account and start"}
        </Button>
      </form>
    </AuthLayout>
  );
}

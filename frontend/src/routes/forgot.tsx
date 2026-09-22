import { zodResolver } from "@hookform/resolvers/zod";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { forgotPassword } from "@/api/auth";
import { errorMessage } from "@/api/client";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { TextLink } from "@/components/auth/TextLink";
import { FormAlert } from "@/components/forms/FormAlert";
import { TextField } from "@/components/forms/TextField";
import { Button } from "@/components/ui/button";
import { emailSchema, type EmailValues } from "@/features/auth/schemas";

export const Route = createFileRoute("/forgot")({
  component: ForgotPassword,
  staticData: { title: "Reset your password" },
});

function ForgotPassword() {
  const [sent, setSent] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const form = useForm<EmailValues>({
    resolver: zodResolver(emailSchema),
    defaultValues: { email: "" },
  });
  const { errors, isSubmitting } = form.formState;

  const onSubmit = form.handleSubmit(async ({ email }) => {
    setProblem(null);
    try {
      await forgotPassword(email);
      setSent(true);
    } catch (error) {
      setProblem(errorMessage(error));
    }
  });

  return (
    <AuthLayout
      title="Reset your password"
      description="We will email you a link to choose a new one."
      footer={<TextLink to="/login">Back to sign in</TextLink>}
    >
      {sent ? (
        <FormAlert tone="success">
          If an account uses that address, a reset link is on its way. It works once and expires in
          30 minutes.
        </FormAlert>
      ) : (
        <form noValidate onSubmit={(event) => void onSubmit(event)} className="grid gap-4">
          {problem && <FormAlert>{problem}</FormAlert>}
          <TextField
            label="Email"
            type="email"
            autoComplete="email"
            error={errors.email?.message}
            {...form.register("email")}
          />
          <Button type="submit" size="lg" className="h-10" disabled={isSubmitting}>
            {isSubmitting ? "Sending…" : "Send reset link"}
          </Button>
        </form>
      )}
    </AuthLayout>
  );
}

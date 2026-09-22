import { zodResolver } from "@hookform/resolvers/zod";
import { Link, createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { isApiError, resetPassword } from "@/api/auth";
import { errorMessage } from "@/api/client";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { TextLink } from "@/components/auth/TextLink";
import { FormAlert } from "@/components/forms/FormAlert";
import { PasswordField } from "@/components/forms/PasswordField";
import { Button } from "@/components/ui/button";
import { PASSWORD_HINT, resetSchema, type ResetValues } from "@/features/auth/schemas";

export const Route = createFileRoute("/reset/$token")({
  component: ResetPassword,
  staticData: { title: "Choose a new password" },
});

function ResetPassword() {
  const { token } = Route.useParams();
  const [done, setDone] = useState(false);
  const [problem, setProblem] = useState<{ message: string; expired: boolean } | null>(null);
  const form = useForm<ResetValues>({
    resolver: zodResolver(resetSchema),
    defaultValues: { password: "" },
  });
  const { errors, isSubmitting } = form.formState;

  const onSubmit = form.handleSubmit(async ({ password }) => {
    setProblem(null);
    try {
      await resetPassword(token, password);
      setDone(true);
    } catch (error) {
      if (isApiError(error, "weak_password")) form.setError("password", { message: error.message });
      else
        setProblem({ message: errorMessage(error), expired: isApiError(error, "invalid_token") });
    }
  });

  if (done) {
    return (
      <AuthLayout title="Password changed">
        <div className="grid gap-4">
          <FormAlert tone="success">
            Your new password is set, and every device was signed out.
          </FormAlert>
          <Button asChild size="lg" className="h-10">
            <Link to="/login">Sign in</Link>
          </Button>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Choose a new password"
      footer={<TextLink to="/login">Back to sign in</TextLink>}
    >
      <form noValidate onSubmit={(event) => void onSubmit(event)} className="grid gap-4">
        {problem && (
          <FormAlert>
            {problem.message} {problem.expired && <TextLink to="/forgot">Send a new link</TextLink>}
          </FormAlert>
        )}
        <PasswordField
          label="New password"
          autoComplete="new-password"
          hint={PASSWORD_HINT}
          error={errors.password?.message}
          {...form.register("password")}
        />
        <Button type="submit" size="lg" className="h-10" disabled={isSubmitting}>
          {isSubmitting ? "Saving…" : "Set new password"}
        </Button>
      </form>
    </AuthLayout>
  );
}

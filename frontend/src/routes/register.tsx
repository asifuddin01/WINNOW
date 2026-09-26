import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { createFileRoute, redirect } from "@tanstack/react-router";
import { MailCheckIcon } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";

import {
  authOptionsQuery,
  startUrl,
  isApiError,
  loadAuthOptions,
  loadMe,
  register,
} from "@/api/auth";
import { errorMessage } from "@/api/client";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { GoogleButton, OrDivider } from "@/components/auth/GoogleButton";
import { TextLink } from "@/components/auth/TextLink";
import { FormAlert } from "@/components/forms/FormAlert";
import { PasswordField } from "@/components/forms/PasswordField";
import { TextField } from "@/components/forms/TextField";
import { Button } from "@/components/ui/button";
import { PASSWORD_HINT, registerSchema, type RegisterValues } from "@/features/auth/schemas";
import { inviteSearch } from "@/lib/search";

export const Route = createFileRoute("/register")({
  validateSearch: inviteSearch,
  beforeLoad: async ({ context }) => {
    const [options, me] = await Promise.all([
      loadAuthOptions(context.queryClient),
      loadMe(context.queryClient),
    ]);
    if (options.needs_setup) redirect({ to: "/setup", throw: true });
    if (me) redirect({ to: "/", throw: true });
  },
  component: Register,
  staticData: { title: "Create an account" },
});

function Register() {
  const { invite } = Route.useSearch();
  const { data: options } = useQuery(authOptionsQuery);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const form = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { name: "", email: "", password: "" },
  });
  const { errors, isSubmitting } = form.formState;

  // An invitation is the way in when registration is by invitation only (guide 8.1).
  if (options && ((options.registration !== "open" && !invite) || options.single_user)) {
    return (
      <AuthLayout
        title="Registration is closed"
        description={
          options.registration === "invite_only"
            ? "This Winnow instance is by invitation. Ask a review owner to invite you."
            : "This Winnow instance is not accepting new accounts."
        }
        footer={<TextLink to="/login">Back to sign in</TextLink>}
      >
        {null}
      </AuthLayout>
    );
  }

  if (sentTo) {
    return (
      <AuthLayout
        title="Check your email"
        footer={<TextLink to="/login">Back to sign in</TextLink>}
      >
        <div className="grid justify-items-center gap-3 text-center">
          <span className="flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
            <MailCheckIcon className="size-6" aria-hidden="true" />
          </span>
          <p className="text-sm">
            We sent a confirmation link to <strong className="font-medium">{sentTo}</strong>. It
            works once and expires in 24 hours.
          </p>
          <p className="text-sm text-muted-foreground">
            You can sign in now; confirming your email lets you join reviews.
          </p>
        </div>
      </AuthLayout>
    );
  }

  const onSubmit = form.handleSubmit(async (values) => {
    setProblem(null);
    try {
      await register({ ...values, ...(invite && { invite_token: invite }) });
      setSentTo(values.email);
    } catch (error) {
      if (isApiError(error, "weak_password")) form.setError("password", { message: error.message });
      else setProblem(errorMessage(error));
    }
  });

  return (
    <AuthLayout
      title="Create your account"
      description="Free for every review, every collaborator."
      footer={
        <>
          Already have an account? <TextLink to="/login">Sign in</TextLink>
        </>
      }
    >
      <form noValidate onSubmit={(event) => void onSubmit(event)} className="grid gap-4">
        {problem && <FormAlert>{problem}</FormAlert>}
        {options?.google_enabled && (
          <>
            <GoogleButton href={startUrl("google")} label="Sign up with Google" />
            <OrDivider />
          </>
        )}
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
          {isSubmitting ? "Creating account…" : "Create account"}
        </Button>
      </form>
    </AuthLayout>
  );
}

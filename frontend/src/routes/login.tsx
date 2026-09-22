import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, redirect, useNavigate } from "@tanstack/react-router";
import { ArrowLeftIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";

import {
  authOptionsQuery,
  isApiError,
  loadAuthOptions,
  loadMe,
  safeRedirect,
  signIn,
} from "@/api/auth";
import { errorMessage } from "@/api/client";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { TextLink } from "@/components/auth/TextLink";
import { FormAlert } from "@/components/forms/FormAlert";
import { PasswordField } from "@/components/forms/PasswordField";
import { TextField } from "@/components/forms/TextField";
import { Button } from "@/components/ui/button";
import { signInSchema, type SignInValues } from "@/features/auth/schemas";
import { redirectSearch } from "@/lib/search";

export const Route = createFileRoute("/login")({
  validateSearch: redirectSearch,
  beforeLoad: async ({ context, search }) => {
    const [options, me] = await Promise.all([
      loadAuthOptions(context.queryClient),
      loadMe(context.queryClient),
    ]);
    if (options.needs_setup) redirect({ to: "/setup", throw: true });
    if (me) redirect({ href: safeRedirect(search.redirect), throw: true });
  },
  component: SignIn,
  staticData: { title: "Sign in" },
});

function SignIn() {
  const { redirect: target } = Route.useSearch();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: options } = useQuery(authOptionsQuery);
  const [step, setStep] = useState<"password" | "code">("password");
  const [problem, setProblem] = useState<string | null>(null);
  const form = useForm<SignInValues>({
    resolver: zodResolver(signInSchema),
    defaultValues: { email: "", password: "", code: "" },
  });
  const { errors, isSubmitting } = form.formState;

  // Moving to the code step: put the cursor where the code goes.
  useEffect(() => {
    if (step === "code") form.setFocus("code");
  }, [step, form]);

  const onSubmit = form.handleSubmit(async ({ email, password, code }) => {
    setProblem(null);
    if (step === "code" && !code.trim()) {
      form.setError("code", { message: "Enter the code from your authenticator app." });
      return;
    }
    try {
      await signIn(queryClient, { email, password, ...(step === "code" && { totp: code.trim() }) });
      await navigate({ href: safeRedirect(target), replace: true });
    } catch (error) {
      if (isApiError(error, "totp_required")) {
        setStep("code");
      } else if (isApiError(error, "invalid_totp")) {
        form.setError("code", { message: error.message });
      } else {
        setProblem(errorMessage(error));
      }
    }
  });

  const canRegister = options?.registration === "open" && !options.single_user;

  return (
    <AuthLayout
      title={step === "password" ? "Sign in to Winnow" : "Two-step verification"}
      description={
        step === "password"
          ? "Pick up your reviews where you left them."
          : `Signing in as ${form.getValues("email")}.`
      }
      footer={
        canRegister && step === "password" ? (
          <>
            New to Winnow? <TextLink to="/register">Create an account</TextLink>
          </>
        ) : undefined
      }
    >
      <form noValidate onSubmit={(event) => void onSubmit(event)} className="grid gap-4">
        {problem && <FormAlert>{problem}</FormAlert>}
        {step === "password" ? (
          <>
            <TextField
              label="Email"
              type="email"
              autoComplete="email"
              error={errors.email?.message}
              {...form.register("email")}
            />
            <PasswordField
              label="Password"
              autoComplete="current-password"
              error={errors.password?.message}
              hint={<TextLink to="/forgot">Forgot your password?</TextLink>}
              {...form.register("password")}
            />
          </>
        ) : (
          <>
            <TextField
              label="Authentication code"
              autoComplete="one-time-code"
              inputMode="text"
              placeholder="123456"
              className="font-mono tracking-widest"
              error={errors.code?.message}
              hint="Open your authenticator app, or enter one of your recovery codes."
              {...form.register("code")}
            />
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="justify-self-start"
              onClick={() => {
                setStep("password");
                form.setValue("code", "");
              }}
            >
              <ArrowLeftIcon aria-hidden="true" />
              Use a different account
            </Button>
          </>
        )}
        <Button type="submit" size="lg" className="mt-1 h-10" disabled={isSubmitting}>
          {isSubmitting ? "Signing in…" : step === "password" ? "Sign in" : "Verify and sign in"}
        </Button>
      </form>
    </AuthLayout>
  );
}

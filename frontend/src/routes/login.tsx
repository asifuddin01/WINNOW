import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { ArrowLeftIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";

import {
  GOOGLE_ERRORS,
  authOptionsQuery,
  finishGoogleSignIn,
  googleStartUrl,
  isApiError,
  loadAuthOptions,
  loadMe,
  meQuery,
  safeRedirect,
  signIn,
} from "@/api/auth";
import { errorMessage } from "@/api/client";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { GoogleButton, OrDivider } from "@/components/auth/GoogleButton";
import { TextLink } from "@/components/auth/TextLink";
import { FormAlert } from "@/components/forms/FormAlert";
import { PasswordField } from "@/components/forms/PasswordField";
import { TextField } from "@/components/forms/TextField";
import { Button } from "@/components/ui/button";
import { signInSchema, type SignInValues } from "@/features/auth/schemas";
import { signInSearch } from "@/lib/search";

export const Route = createFileRoute("/login")({
  validateSearch: signInSearch,
  // Asked for here, not waited on: the form's own code then loads alongside the two
  // answers, instead of after them (one round trip less before anything shows; 2.3 s to
  // first paint on Lighthouse's mobile network). SignIn redirects once they arrive.
  beforeLoad: ({ context }) => {
    void loadAuthOptions(context.queryClient).catch(() => undefined);
    void loadMe(context.queryClient).catch(() => undefined);
  },
  component: SignIn,
  staticData: { title: "Sign in" },
});

function SignIn() {
  const search = Route.useSearch();
  const navigate = useNavigate();
  const { data: options } = useQuery(authOptionsQuery);
  const { data: me } = useQuery(meQuery);
  useEffect(() => {
    // A new instance needs its first account; someone signed in has nothing to do here.
    if (options?.needs_setup) void navigate({ to: "/setup", replace: true });
    else if (me) void navigate({ href: safeRedirect(search.redirect), replace: true });
  }, [options, me, navigate, search.redirect]);
  if (search.step === "google-2fa") return <GoogleTwoFactor />;
  return <PasswordSignIn />;
}

function PasswordSignIn() {
  const { redirect: target, error: googleError } = Route.useSearch();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: options } = useQuery(authOptionsQuery);
  const [step, setStep] = useState<"password" | "code">("password");
  const [problem, setProblem] = useState<string | null>(
    googleError ? (GOOGLE_ERRORS[googleError] ?? GOOGLE_ERRORS.google_failed ?? null) : null,
  );
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
        {step === "password" && options?.google_enabled && (
          <>
            <GoogleButton href={googleStartUrl(target)} label="Continue with Google" />
            <OrDivider />
          </>
        )}
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

/** A Google sign-in reached an account with two-factor authentication: ask for the code. */
function GoogleTwoFactor() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [code, setCode] = useState("");
  const [problem, setProblem] = useState<{ message: string; expired: boolean } | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setProblem(null);
    if (!code.trim()) {
      setProblem({ message: "Enter the code from your authenticator app.", expired: false });
      return;
    }
    setBusy(true);
    try {
      const { redirect: next } = await finishGoogleSignIn(queryClient, code.trim());
      await navigate({ href: next, replace: true });
    } catch (error) {
      setProblem({
        message: errorMessage(error),
        expired: isApiError(error, "google_pending_expired"),
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout
      title="Two-step verification"
      description="Google confirmed who you are. Your account also asks for a code."
      footer={<TextLink to="/login">Start over</TextLink>}
    >
      <form
        noValidate
        className="grid gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        {problem && (
          <FormAlert>
            {problem.message} {problem.expired && <TextLink to="/login">Sign in again</TextLink>}
          </FormAlert>
        )}
        <TextField
          label="Authentication code"
          autoComplete="one-time-code"
          placeholder="123456"
          className="font-mono tracking-widest"
          hint="Open your authenticator app, or enter one of your recovery codes."
          value={code}
          onChange={(event) => {
            setCode(event.target.value);
          }}
        />
        <Button type="submit" size="lg" className="h-10" disabled={busy}>
          {busy ? "Checking…" : "Verify and sign in"}
        </Button>
      </form>
    </AuthLayout>
  );
}

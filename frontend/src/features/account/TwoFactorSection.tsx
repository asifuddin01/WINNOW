import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldCheckIcon, ShieldOffIcon } from "lucide-react";
import { useState, type SyntheticEvent } from "react";
import { toast } from "sonner";

import {
  beginTwoFactorSetup,
  disableTwoFactor,
  enableTwoFactor,
  meQuery,
  regenerateRecoveryCodes,
} from "@/api/auth";
import { errorMessage } from "@/api/client";
import { FormAlert } from "@/components/forms/FormAlert";
import { PasswordField } from "@/components/forms/PasswordField";
import { TextField } from "@/components/forms/TextField";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RecoveryCodes } from "@/features/account/RecoveryCodes";
import { Section } from "@/features/account/Section";

type Mode = "idle" | "disable" | "regenerate";

function field(event: SyntheticEvent<HTMLFormElement>, name: string): string {
  const value = new FormData(event.currentTarget).get(name);
  return typeof value === "string" ? value.trim() : "";
}

export function TwoFactorSection() {
  const queryClient = useQueryClient();
  const { data: me } = useQuery(meQuery);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [mode, setMode] = useState<Mode>("idle");

  const setup = useMutation({ mutationFn: beginTwoFactorSetup });
  const enable = useMutation({
    mutationFn: (code: string) => enableTwoFactor(queryClient, code),
    onSuccess: (newCodes) => {
      setCodes(newCodes);
      setup.reset();
    },
  });
  const disable = useMutation({
    mutationFn: (input: { password: string; code: string }) => disableTwoFactor(queryClient, input),
    onSuccess: () => {
      setMode("idle");
      toast.success("Two-factor authentication is off.");
    },
  });
  const regenerate = useMutation({
    mutationFn: (code: string) => regenerateRecoveryCodes(queryClient, code),
    onSuccess: (newCodes) => {
      setMode("idle");
      setCodes(newCodes);
    },
  });

  if (!me) return null;
  const status = me.totp_enabled ? (
    <Badge variant="secondary" className="gap-1">
      <ShieldCheckIcon aria-hidden="true" /> On
    </Badge>
  ) : (
    <Badge variant="outline" className="gap-1">
      <ShieldOffIcon aria-hidden="true" /> Off
    </Badge>
  );

  return (
    <Section
      title="Two-factor authentication"
      description="Ask for a code from an authenticator app (Google Authenticator, 1Password, Aegis…) when signing in."
      aside={status}
    >
      {codes ? (
        <RecoveryCodes
          codes={codes}
          onDone={() => {
            setCodes(null);
          }}
        />
      ) : setup.data ? (
        <form
          className="grid gap-5"
          onSubmit={(event) => {
            event.preventDefault();
            enable.mutate(field(event, "code"));
          }}
        >
          <ol className="grid list-decimal gap-5 pl-5 text-sm">
            <li className="grid gap-3">
              <span>Scan this QR code with your authenticator app.</span>
              <img
                src={setup.data.qr_code}
                alt="QR code to add Winnow to your authenticator app"
                className="size-44 rounded-lg border border-border bg-white p-1"
              />
              <span className="text-muted-foreground">
                Or type this key:{" "}
                <code
                  className="rounded bg-muted px-1.5 py-0.5 font-mono text-foreground select-all"
                  data-testid="totp-secret"
                >
                  {setup.data.secret.match(/.{1,4}/g)?.join(" ")}
                </code>
              </span>
            </li>
            <li className="grid max-w-xs gap-3">
              <span>Enter the 6-digit code the app shows.</span>
              <TextField
                label="Code from the app"
                name="code"
                autoComplete="one-time-code"
                inputMode="numeric"
                className="font-mono tracking-widest"
                error={enable.isError ? errorMessage(enable.error) : undefined}
              />
            </li>
          </ol>
          <div className="flex gap-2">
            <Button type="submit" disabled={enable.isPending}>
              {enable.isPending ? "Checking…" : "Turn on"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setup.reset();
                enable.reset();
              }}
            >
              Cancel
            </Button>
          </div>
        </form>
      ) : !me.totp_enabled ? (
        <div className="grid gap-3">
          {setup.isError && <FormAlert>{errorMessage(setup.error)}</FormAlert>}
          <Button
            className="justify-self-start"
            disabled={setup.isPending}
            onClick={() => {
              setup.mutate();
            }}
          >
            Set up two-factor authentication
          </Button>
        </div>
      ) : mode === "disable" ? (
        <form
          className="grid max-w-sm gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            disable.mutate({ password: field(event, "password"), code: field(event, "code") });
          }}
        >
          {disable.isError && <FormAlert>{errorMessage(disable.error)}</FormAlert>}
          <PasswordField label="Password" name="password" autoComplete="current-password" />
          <TextField
            label="Authenticator or recovery code"
            name="code"
            autoComplete="one-time-code"
          />
          <div className="flex gap-2">
            <Button type="submit" variant="destructive" disabled={disable.isPending}>
              Turn off two-factor
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setMode("idle");
              }}
            >
              Cancel
            </Button>
          </div>
        </form>
      ) : mode === "regenerate" ? (
        <form
          className="grid max-w-sm gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            regenerate.mutate(field(event, "code"));
          }}
        >
          {regenerate.isError && <FormAlert>{errorMessage(regenerate.error)}</FormAlert>}
          <TextField
            label="Authenticator or recovery code"
            name="code"
            autoComplete="one-time-code"
            hint="Your current recovery codes stop working."
          />
          <div className="flex gap-2">
            <Button type="submit" disabled={regenerate.isPending}>
              Make new codes
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setMode("idle");
              }}
            >
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <div className="grid gap-3">
          <p className="text-sm">
            {me.recovery_codes_left} of 10 recovery codes left.
            {me.recovery_codes_left <= 3 && " Make new ones before you run out."}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              onClick={() => {
                setMode("regenerate");
              }}
            >
              New recovery codes
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                setMode("disable");
              }}
            >
              Turn off
            </Button>
          </div>
        </div>
      )}
    </Section>
  );
}

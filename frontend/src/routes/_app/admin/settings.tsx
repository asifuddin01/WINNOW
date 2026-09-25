import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useId, useState } from "react";

import {
  adminKeys,
  instanceSettingsQuery,
  updateInstanceSettings,
  type InstanceSettings,
} from "@/api/admin";
import { errorMessage } from "@/api/client";
import { FormAlert } from "@/components/forms/FormAlert";
import { SelectField } from "@/components/forms/SelectField";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useProjectMutation } from "@/features/projects/use-project-mutation";

export const Route = createFileRoute("/_app/admin/settings")({
  component: InstanceSettingsPage,
  staticData: { title: "Settings" },
});

const MODES = {
  open: "Open: anyone can create an account",
  invite_only: "By invitation: only people invited to a review",
  closed: "Closed: no new accounts",
} as const;

function InstanceSettingsPage() {
  const { data, error, isPending } = useQuery(instanceSettingsQuery);
  if (isPending) return <Skeleton className="h-64 w-full rounded-xl" aria-busy="true" />;
  if (error) return <FormAlert>{errorMessage(error)}</FormAlert>;
  return (
    <div className="grid gap-6">
      <Live key={JSON.stringify([data.registration, data.unpaywall_email])} settings={data} />
      <Environment settings={data} />
    </div>
  );
}

function From({ source }: { source: "admin" | "environment" }) {
  return (
    <Badge variant={source === "admin" ? "default" : "outline"}>
      {source === "admin" ? "Set here" : "From .env"}
    </Badge>
  );
}

function Live({ settings }: { settings: InstanceSettings }) {
  const id = useId();
  const stored = settings.unpaywall_email.value;
  const [email, setEmail] = useState(typeof stored === "string" ? stored : "");
  const save = useProjectMutation(updateInstanceSettings, {
    invalidate: [adminKeys.settings],
    success: "Saved.",
  });
  const registration = String(settings.registration.value) as keyof typeof MODES;
  return (
    <section
      aria-labelledby={`${id}-live`}
      className="grid gap-5 rounded-xl border border-border bg-card p-5"
    >
      <div>
        <h2 id={`${id}-live`} className="text-base font-semibold">
          While Winnow runs
        </h2>
        <p className="text-sm text-muted-foreground">
          These take effect at once, without a restart, and win over the values in .env.
        </p>
      </div>
      <div className="grid max-w-md gap-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Registration</span>
          <From source={settings.registration.source} />
        </div>
        <SelectField
          label="Who can create an account"
          value={registration}
          options={Object.entries(MODES).map(([value, label]) => ({
            value: value as keyof typeof MODES,
            label,
          }))}
          onChange={(next) => {
            save.mutate({ registration: next });
          }}
        />
        {settings.registration.source === "admin" && (
          <div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                save.mutate({ registration: "environment" });
              }}
            >
              Use the value in .env instead
            </Button>
          </div>
        )}
      </div>
      <form
        className="grid max-w-md gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate({ unpaywall_email: email.trim() });
        }}
      >
        <div className="flex items-center gap-2">
          <Label htmlFor={`${id}-email`}>Email for Unpaywall</Label>
          <From source={settings.unpaywall_email.source} />
        </div>
        <Input
          id={`${id}-email`}
          type="email"
          value={email}
          aria-describedby={`${id}-email-hint`}
          onChange={(event) => {
            setEmail(event.target.value);
          }}
        />
        <p id={`${id}-email-hint`} className="text-xs text-muted-foreground">
          Unpaywall asks for a contact address with each lookup of a free full text. Leave empty to
          use the value in .env.
        </p>
        <div>
          <Button type="submit" size="sm" disabled={save.isPending}>
            Save email
          </Button>
        </div>
      </form>
      {save.isError && <FormAlert>{errorMessage(save.error)}</FormAlert>}
    </section>
  );
}

function Environment({ settings }: { settings: InstanceSettings }) {
  const id = useId();
  const yes = (on: boolean) => (on ? "Yes" : "No");
  const rows: [string, string][] = [
    ["Public address", settings.public_url],
    ["Single-user mode", yes(settings.single_user)],
    [
      "Email sending",
      settings.email_configured ? `Yes, from ${settings.email_from}` : "Not set up",
    ],
    [
      "File storage",
      settings.storage_backend === "s3" ? "S3-compatible bucket" : "This server's disk",
    ],
    [
      "Virus scanner (ClamAV)",
      settings.virus_scanner ? "Yes" : "Not set up: PDFs are marked unscanned",
    ],
    ["Free full-text lookup", yes(settings.open_access_lookup)],
    [
      "AI suggestions",
      settings.llm_provider === "none"
        ? "Off"
        : `${settings.llm_provider}${settings.llm_model ? `, ${settings.llm_model}` : ""}${settings.llm_configured ? "" : " (not fully set up)"}`,
    ],
    ["Largest upload", `${settings.max_upload_mb.toLocaleString()} MB`],
    ["Largest PDF", `${settings.max_pdf_mb.toLocaleString()} MB`],
    ["Largest backup to restore", `${settings.max_backup_mb.toLocaleString()} MB`],
    ["Winnow version", settings.version],
  ];
  return (
    <section
      aria-labelledby={`${id}-env`}
      className="grid gap-3 rounded-xl border border-border bg-card p-5"
    >
      <div>
        <h2 id={`${id}-env`} className="text-base font-semibold">
          From the environment
        </h2>
        <p className="text-sm text-muted-foreground">
          Set in .env and read at start-up (see docs/deploy.md). Secrets such as passwords and API
          keys are never shown here.
        </p>
      </div>
      <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[14rem_1fr]">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="break-words">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

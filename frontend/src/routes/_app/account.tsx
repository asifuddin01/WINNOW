import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { CircleCheckIcon, MailWarningIcon } from "lucide-react";

import { meQuery } from "@/api/auth";
import { Badge } from "@/components/ui/badge";
import { PasswordSection } from "@/features/account/PasswordSection";
import { Section } from "@/features/account/Section";
import { SessionsSection } from "@/features/account/SessionsSection";
import { TwoFactorSection } from "@/features/account/TwoFactorSection";

export const Route = createFileRoute("/_app/account")({
  component: Account,
  staticData: { title: "Account" },
});

function Account() {
  const { data: me } = useQuery(meQuery);
  if (!me) return null;
  return (
    <div className="mx-auto grid w-full max-w-3xl gap-6 px-4 py-8 md:px-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Account and security</h1>
        <p className="mt-1 text-muted-foreground">
          Your sign-in details and the devices using them.
        </p>
      </div>
      <Section title="Profile">
        <dl className="grid gap-3 text-sm sm:grid-cols-[8rem_1fr]">
          <dt className="text-muted-foreground">Name</dt>
          <dd>{me.name}</dd>
          <dt className="text-muted-foreground">Email</dt>
          <dd className="flex flex-wrap items-center gap-2">
            {me.email}
            {me.email_verified ? (
              <Badge variant="secondary" className="gap-1">
                <CircleCheckIcon aria-hidden="true" /> Confirmed
              </Badge>
            ) : (
              <Badge variant="outline" className="gap-1">
                <MailWarningIcon aria-hidden="true" /> Not confirmed
              </Badge>
            )}
          </dd>
          <dt className="text-muted-foreground">Signs in with</dt>
          <dd className="flex flex-wrap gap-2">
            {me.has_password && <Badge variant="secondary">Password</Badge>}
            {me.google_linked && <Badge variant="secondary">Google</Badge>}
          </dd>
        </dl>
      </Section>
      <PasswordSection />
      <TwoFactorSection />
      <SessionsSection />
    </div>
  );
}

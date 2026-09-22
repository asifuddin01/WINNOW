import { useQuery } from "@tanstack/react-query";
import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import { MailOpenIcon } from "lucide-react";

import { isApiError, meQuery } from "@/api/auth";
import { errorMessage } from "@/api/client";
import { acceptInvite, invitePreviewQuery, projectKeys } from "@/api/projects";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { TextLink } from "@/components/auth/TextLink";
import { FormAlert } from "@/components/forms/FormAlert";
import { Button } from "@/components/ui/button";
import { useProjectMutation } from "@/features/projects/use-project-mutation";
import { ROLES } from "@/features/projects/wording";

export const Route = createFileRoute("/invite/$token")({
  component: Invitation,
  staticData: { title: "Invitation" },
});

function Invitation() {
  const { token } = Route.useParams();
  const navigate = useNavigate();
  const { data: me } = useQuery(meQuery);
  const { data: invite, isPending, error } = useQuery(invitePreviewQuery(token));
  const accept = useProjectMutation(() => acceptInvite(token), {
    invalidate: [projectKeys.list],
    success: "You have joined the review.",
  });
  const here = `/invite/${token}`;

  if (isPending) return <AuthLayout title="Invitation">Checking the invitation…</AuthLayout>;

  if (error) {
    return (
      <AuthLayout
        title="This invitation does not work"
        description={
          isApiError(error) ? error.message : "The link may have been withdrawn or mistyped."
        }
        footer={<TextLink to="/">Go to my reviews</TextLink>}
      >
        <p className="text-sm text-muted-foreground">
          Ask whoever invited you to send a new invitation.
        </p>
      </AuthLayout>
    );
  }

  const description = (
    <>
      {invite.inviter_name ?? "Someone"} invited{" "}
      <span className="font-medium text-foreground">{invite.email_hint}</span> to join{" "}
      <span className="font-medium text-foreground">{invite.project_title}</span> as{" "}
      {ROLES[invite.role].toLowerCase()}.
    </>
  );

  if (invite.state !== "pending") {
    return (
      <AuthLayout
        title={invite.state === "accepted" ? "Already accepted" : "This invitation has expired"}
        description={description}
        footer={<TextLink to="/">Go to my reviews</TextLink>}
      >
        <p className="text-sm text-muted-foreground">
          {invite.state === "accepted"
            ? "This link has been used. If the review is yours, you will find it in your list."
            : "Invitations last a week. Ask for a new one."}
        </p>
      </AuthLayout>
    );
  }

  if (!me) {
    return (
      <AuthLayout
        title="You are invited"
        description={description}
        footer={
          <>
            Signing in with a different address? The invitation only works for {invite.email_hint}.
          </>
        }
      >
        <div className="grid gap-3">
          <Button asChild>
            <Link to="/login" search={{ redirect: here }}>
              Sign in to accept
            </Link>
          </Button>
          <Button asChild variant="outline">
            <Link to="/register" search={{ invite: token }}>
              Create an account
            </Link>
          </Button>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="You are invited"
      description={description}
      footer={
        <>
          Signed in as {me.email}. <TextLink to="/">Not you?</TextLink>
        </>
      }
    >
      <div className="grid gap-3">
        {accept.isError && <FormAlert>{errorMessage(accept.error)}</FormAlert>}
        {!me.email_verified && (
          <FormAlert tone="warning">
            Confirm your email address first — we sent a link when you signed up.
          </FormAlert>
        )}
        <Button
          disabled={accept.isPending}
          onClick={() => {
            accept.mutate(undefined, {
              onSuccess: (pid) => void navigate({ to: "/p/$pid", params: { pid } }),
            });
          }}
        >
          <MailOpenIcon aria-hidden="true" />
          {accept.isPending ? "Joining…" : "Accept invitation"}
        </Button>
      </div>
    </AuthLayout>
  );
}

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, createFileRoute } from "@tanstack/react-router";
import { MailCheckIcon } from "lucide-react";

import { meQuery, verifyEmail } from "@/api/auth";
import { errorMessage } from "@/api/client";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { TextLink } from "@/components/auth/TextLink";
import { FormAlert } from "@/components/forms/FormAlert";
import { Button } from "@/components/ui/button";

export const Route = createFileRoute("/verify/$token")({
  component: VerifyEmail,
  staticData: { title: "Confirm your email" },
});

/**
 * Confirms on a click, not on page load: mail security scanners open links, and a link
 * that confirmed itself would be spent before its owner saw it.
 */
function VerifyEmail() {
  const { token } = Route.useParams();
  const queryClient = useQueryClient();
  const { data: me } = useQuery(meQuery);
  const confirm = useMutation({ mutationFn: () => verifyEmail(queryClient, token) });

  if (confirm.isSuccess) {
    return (
      <AuthLayout title="Email confirmed">
        <div className="grid justify-items-center gap-4 text-center">
          <span className="flex size-12 items-center justify-center rounded-full bg-include-muted text-include">
            <MailCheckIcon className="size-6" aria-hidden="true" />
          </span>
          <p className="text-sm">
            <strong className="font-medium">{confirm.data.email}</strong> is confirmed. You can now
            join reviews.
          </p>
          <Button asChild size="lg" className="h-10 w-full">
            <Link to={me ? "/" : "/login"}>{me ? "Go to my reviews" : "Sign in"}</Link>
          </Button>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Confirm your email"
      description="One click and your address is confirmed."
      footer={<TextLink to={me ? "/" : "/login"}>{me ? "Back to my reviews" : "Sign in"}</TextLink>}
    >
      <div className="grid gap-4">
        {confirm.isError && (
          <FormAlert>
            {errorMessage(confirm.error)} Signed-in accounts can send a new link from the banner at
            the top of every page.
          </FormAlert>
        )}
        <Button
          size="lg"
          className="h-10"
          disabled={confirm.isPending}
          onClick={() => {
            confirm.mutate();
          }}
        >
          {confirm.isPending ? "Confirming…" : "Confirm email address"}
        </Button>
      </div>
    </AuthLayout>
  );
}

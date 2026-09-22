import { useMutation, useQuery } from "@tanstack/react-query";
import { MailWarningIcon } from "lucide-react";

import { meQuery, resendVerification } from "@/api/auth";
import { errorMessage } from "@/api/client";
import { Button } from "@/components/ui/button";

/** Unconfirmed accounts can use Winnow but not join reviews (guide 8.1). */
export function VerifyEmailBanner() {
  const { data: me } = useQuery(meQuery);
  const resend = useMutation({ mutationFn: resendVerification });
  if (!me || me.email_verified) return null;

  let status = "Confirm your email address to join reviews. Check your inbox for the link.";
  if (resend.isSuccess) status = `We sent a new link to ${me.email}.`;
  if (resend.isError) status = errorMessage(resend.error);

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-border bg-muted px-4 py-2 text-sm">
      <MailWarningIcon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <p role="status" className="min-w-0 flex-1">
        {status}
      </p>
      {!resend.isSuccess && (
        <Button
          variant="outline"
          size="sm"
          disabled={resend.isPending}
          onClick={() => {
            resend.mutate();
          }}
        >
          {resend.isPending ? "Sending…" : "Send a new link"}
        </Button>
      )}
    </div>
  );
}

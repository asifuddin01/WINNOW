import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { LaptopIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { revokeSession, sessionsQuery, signOut } from "@/api/auth";
import { errorMessage } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Section } from "@/features/account/Section";
import { describeDevice, timeAgo } from "@/lib/format";

export function SessionsSection() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const sessions = useQuery(sessionsQuery);
  const [confirming, setConfirming] = useState(false);
  const revoke = useMutation({
    mutationFn: (id: string) => revokeSession(queryClient, id),
    onSuccess: () => toast.success("That device was signed out."),
    onError: (error) => toast.error(errorMessage(error)),
  });
  const everywhere = useMutation({
    mutationFn: () => signOut(queryClient, { everywhere: true }),
    onSuccess: () => navigate({ to: "/login", replace: true }),
    onError: (error) => toast.error(errorMessage(error)),
  });

  return (
    <Section title="Signed-in devices" description="Sign out of any device you do not recognise.">
      {sessions.isPending ? (
        <div className="grid gap-2">
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
        </div>
      ) : sessions.isError ? (
        <p className="text-sm text-destructive">{errorMessage(sessions.error)}</p>
      ) : (
        <ul className="divide-y divide-border rounded-lg border border-border">
          {sessions.data.map((session) => (
            <li key={session.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
              <LaptopIcon className="size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">
                  {describeDevice(session.user_agent)}
                  {session.current && (
                    <Badge variant="secondary" className="ml-2 align-middle">
                      This device
                    </Badge>
                  )}
                </p>
                <p className="text-xs text-muted-foreground">
                  {session.ip ?? "Unknown address"} · active {timeAgo(session.last_seen_at)}
                </p>
              </div>
              {!session.current && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={revoke.isPending}
                  aria-label={`Sign out ${describeDevice(session.user_agent)}, last active ${timeAgo(session.last_seen_at)}`}
                  onClick={() => {
                    revoke.mutate(session.id);
                  }}
                >
                  Sign out
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {confirming ? (
          <>
            <p className="text-sm">Sign out of every device, including this one?</p>
            <Button
              variant="destructive"
              size="sm"
              disabled={everywhere.isPending}
              onClick={() => {
                everywhere.mutate();
              }}
            >
              Sign out everywhere
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setConfirming(false);
              }}
            >
              Cancel
            </Button>
          </>
        ) : (
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setConfirming(true);
            }}
          >
            Sign out everywhere
          </Button>
        )}
      </div>
    </Section>
  );
}

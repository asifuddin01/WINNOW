import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { MoreHorizontalIcon, SearchIcon } from "lucide-react";
import { useDeferredValue, useId, useState } from "react";

import { actOnUser, adminKeys, adminUsersQuery, type AdminUser } from "@/api/admin";
import { meQuery } from "@/api/auth";
import { errorMessage } from "@/api/client";
import { FormAlert } from "@/components/forms/FormAlert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/features/projects/ConfirmDialog";
import { useProjectMutation } from "@/features/projects/use-project-mutation";
import { timeAgo } from "@/lib/format";

export const Route = createFileRoute("/_app/admin/")({
  component: People,
  staticData: { title: "People" },
});

function People() {
  const id = useId();
  const [text, setText] = useState("");
  const q = useDeferredValue(text.trim());
  const { data, error, isPending, hasNextPage, fetchNextPage, isFetchingNextPage } =
    useInfiniteQuery(adminUsersQuery(q));
  const users = data?.pages.flatMap((page) => page.items) ?? [];
  const total = data?.pages[0]?.total ?? 0;

  return (
    <div className="grid gap-4">
      <div className="grid max-w-md gap-1.5">
        <Label htmlFor={`${id}-q`}>Find someone</Label>
        <div className="relative">
          <SearchIcon
            className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            id={`${id}-q`}
            type="search"
            className="pl-8"
            placeholder="Name or email"
            value={text}
            onChange={(event) => {
              setText(event.target.value);
            }}
          />
        </div>
      </div>
      {isPending ? (
        <Skeleton className="h-64 w-full rounded-xl" aria-busy="true" />
      ) : error ? (
        <FormAlert>{errorMessage(error)}</FormAlert>
      ) : (
        <>
          <p className="text-sm text-muted-foreground" role="status">
            {total.toLocaleString()} {total === 1 ? "account" : "accounts"}
          </p>
          <div className="overflow-x-auto rounded-xl border border-border bg-card">
            <table className="w-full min-w-[40rem] text-sm">
              <caption className="sr-only">Accounts on this Winnow</caption>
              <thead className="text-left text-xs text-muted-foreground">
                <tr>
                  <th scope="col" className="px-4 py-2 font-medium">
                    Person
                  </th>
                  <th scope="col" className="px-4 py-2 font-medium">
                    Account
                  </th>
                  <th scope="col" className="px-4 py-2 text-right font-medium">
                    Reviews
                  </th>
                  <th scope="col" className="px-4 py-2 font-medium">
                    Joined
                  </th>
                  <th scope="col" className="px-4 py-2">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <Row key={user.id} user={user} q={q} />
                ))}
              </tbody>
            </table>
          </div>
          {hasNextPage && (
            <div>
              <Button
                variant="outline"
                disabled={isFetchingNextPage}
                onClick={() => {
                  void fetchNextPage();
                }}
              >
                {isFetchingNextPage ? "Loading…" : "Show more"}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

type Action = "disable" | "enable" | "reset-2fa" | "sign-out";

const CONFIRM: Record<Action, { title: string; body: string; label: string; done: string }> = {
  disable: {
    title: "Disable this account?",
    body: "They are signed out everywhere and cannot sign in until the account is enabled again. Their reviews and work are untouched.",
    label: "Disable",
    done: "Account disabled.",
  },
  enable: {
    title: "Enable this account?",
    body: "They can sign in again.",
    label: "Enable",
    done: "Account enabled.",
  },
  "reset-2fa": {
    title: "Reset two-factor authentication?",
    body: "For someone who lost their authenticator and their recovery codes. They are signed out, emailed, and sign in with their password alone until they set it up again. Check who is asking first.",
    label: "Reset two-factor",
    done: "Two-factor authentication reset.",
  },
  "sign-out": {
    title: "Sign them out everywhere?",
    body: "Every session on every device ends now. They can sign in again.",
    label: "Sign out everywhere",
    done: "Signed out everywhere.",
  },
};

function Row({ user, q }: { user: AdminUser; q: string }) {
  const { data: me } = useQuery(meQuery);
  const [asking, setAsking] = useState<Action | null>(null);
  const act = useProjectMutation((action: Action) => actOnUser(user.id, action), {
    invalidate: [adminKeys.users(q)],
    success: asking ? CONFIRM[asking].done : undefined,
  });
  const self = me?.id === user.id;
  const actions: Action[] = [
    ...(self ? [] : [user.disabled ? ("enable" as const) : ("disable" as const)]),
    ...(user.two_factor ? ["reset-2fa" as const] : []),
    ...(self ? [] : ["sign-out" as const]),
  ];
  return (
    <tr className="border-t border-border align-top">
      <th scope="row" className="px-4 py-3 text-left font-normal">
        <span className="font-medium">{user.name}</span>
        {self && <span className="text-muted-foreground"> (you)</span>}
        <br />
        <span className="text-muted-foreground">{user.email}</span>
      </th>
      <td className="px-4 py-3">
        <span className="flex flex-wrap gap-1">
          {user.is_instance_admin && <Badge>Admin</Badge>}
          {user.disabled && <Badge variant="destructive">Disabled</Badge>}
          {user.two_factor && <Badge variant="secondary">Two-factor on</Badge>}
          {!user.email_verified && <Badge variant="outline">Email not confirmed</Badge>}
        </span>
      </td>
      <td className="px-4 py-3 text-right tabular-nums">{user.reviews}</td>
      <td className="px-4 py-3 text-muted-foreground">{timeAgo(user.created_at)}</td>
      <td className="px-4 py-3 text-right">
        {actions.length > 0 && (
          <DropdownMenu modal={false}>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${user.name}`}>
                <MoreHorizontalIcon aria-hidden="true" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {actions.map((action) => (
                <DropdownMenuItem
                  key={action}
                  onSelect={() => {
                    setAsking(action);
                  }}
                >
                  {CONFIRM[action].label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
        {asking && (
          <ConfirmDialog
            open
            onOpenChange={(open) => {
              if (!open) setAsking(null);
            }}
            title={CONFIRM[asking].title}
            description={`${user.name} (${user.email}): ${CONFIRM[asking].body}`}
            confirmLabel={CONFIRM[asking].label}
            destructive={asking !== "enable"}
            onConfirm={() => {
              act.mutate(asking);
              setAsking(null);
            }}
          />
        )}
      </td>
    </tr>
  );
}

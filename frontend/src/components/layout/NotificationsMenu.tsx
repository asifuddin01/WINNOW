import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { BellIcon, CheckCheckIcon } from "lucide-react";
import { useState } from "react";

import { markAllRead, markRead, noticeKeys, noticesQuery, unreadQuery } from "@/api/notifications";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { describeNotice } from "@/features/notifications/wording";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

/** The bell (guide 8.17): unread notices, newest first; opening one marks it read. */
export function NotificationsMenu() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const { data: unread } = useQuery(unreadQuery);
  const { data: page, isPending } = useQuery({ ...noticesQuery, enabled: open });
  const count = unread?.unread ?? 0;
  const refresh = () => queryClient.invalidateQueries({ queryKey: noticeKeys.all });

  return (
    // Not modal: the page stays in the accessibility tree while it is open (a modal menu
    // hides it with aria-hidden while its links can still take focus).
    <DropdownMenu open={open} onOpenChange={setOpen} modal={false}>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative"
          aria-label={count ? `Notifications, ${count} unread` : "Notifications"}
        >
          <BellIcon aria-hidden="true" />
          {count > 0 && (
            <span
              aria-hidden="true"
              className="absolute top-1 right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[0.65rem] leading-none font-semibold text-primary-foreground"
            >
              {count > 99 ? "99+" : count}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-[min(24rem,calc(100vw-2rem))]">
        <DropdownMenuLabel className="text-sm font-semibold text-foreground">
          Notifications
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {isPending ? (
          <p className="px-2 py-3 text-sm text-muted-foreground">Loading…</p>
        ) : !page || page.items.length === 0 ? (
          <p className="px-2 py-3 text-sm text-muted-foreground">
            Nothing yet. Conflicts to resolve, mentions, invitations and finished imports appear
            here.
          </p>
        ) : (
          <div className="max-h-[60vh] overflow-y-auto">
            {page.items.map((notice) => {
              const { text, to } = describeNotice(notice);
              return (
                <DropdownMenuItem
                  key={notice.id}
                  className="items-start gap-2 py-2"
                  onSelect={() => {
                    if (!notice.read) void markRead(notice.id).then(refresh);
                    if (to) void navigate({ to });
                  }}
                >
                  <span
                    aria-hidden="true"
                    className={cn(
                      "mt-1.5 size-2 shrink-0 rounded-full",
                      notice.read ? "bg-transparent" : "bg-primary",
                    )}
                  />
                  <span className="grid min-w-0 gap-0.5">
                    <span className={cn("text-sm", !notice.read && "font-medium")}>
                      {text}
                      {!notice.read && <span className="sr-only"> (unread)</span>}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {timeAgo(notice.updated_at)}
                    </span>
                  </span>
                </DropdownMenuItem>
              );
            })}
          </div>
        )}
        <DropdownMenuSeparator />
        {count > 0 && (
          <DropdownMenuItem
            onSelect={(event) => {
              // Stays open, so the notices can be seen turning read.
              event.preventDefault();
              void markAllRead().then(refresh);
            }}
          >
            <CheckCheckIcon aria-hidden="true" /> Mark all as read
          </DropdownMenuItem>
        )}
        <DropdownMenuItem asChild>
          <Link to="/account" hash="notifications" className="text-sm">
            Email digest settings
          </Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

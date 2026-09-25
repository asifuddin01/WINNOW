import { SearchIcon } from "lucide-react";

import { NotificationsMenu } from "@/components/layout/NotificationsMenu";
import { Breadcrumbs } from "@/components/layout/PageTitle";
import { ThemeMenu } from "@/components/layout/ThemeMenu";
import { UserMenu } from "@/components/layout/UserMenu";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";

const MAC = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

export function TopBar({ onSearch }: { onSearch?: () => void }) {
  return (
    <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2 border-b border-border bg-background/95 px-3 backdrop-blur supports-[backdrop-filter]:bg-background/80 md:px-4">
      <SidebarTrigger className="-ml-1 size-9" />
      <Separator
        orientation="vertical"
        className="mr-1 data-vertical:h-5 data-vertical:self-center"
      />
      <Breadcrumbs />
      <div className="ml-auto flex items-center gap-1">
        {onSearch && (
          <Button
            variant="outline"
            size="sm"
            className="gap-2 text-muted-foreground"
            aria-keyshortcuts={MAC ? "Meta+K" : "Control+K"}
            onClick={onSearch}
          >
            <SearchIcon aria-hidden="true" />
            <span className="hidden sm:inline">Search or jump to…</span>
            <span className="sr-only sm:hidden">Search or jump to</span>
            <kbd className="hidden rounded border border-border px-1 font-sans text-xs sm:inline">
              {MAC ? "⌘K" : "Ctrl K"}
            </kbd>
          </Button>
        )}
        <NotificationsMenu />
        <ThemeMenu />
        <UserMenu />
      </div>
    </header>
  );
}

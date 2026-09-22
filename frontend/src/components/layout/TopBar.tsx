import { Breadcrumbs } from "@/components/layout/PageTitle";
import { ThemeMenu } from "@/components/layout/ThemeMenu";
import { UserMenu } from "@/components/layout/UserMenu";
import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";

export function TopBar() {
  return (
    <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2 border-b border-border bg-background/95 px-3 backdrop-blur supports-[backdrop-filter]:bg-background/80 md:px-4">
      <SidebarTrigger className="-ml-1 size-9" />
      <Separator
        orientation="vertical"
        className="mr-1 data-vertical:h-5 data-vertical:self-center"
      />
      <Breadcrumbs />
      <div className="ml-auto flex items-center gap-1">
        <ThemeMenu />
        <UserMenu />
      </div>
    </header>
  );
}

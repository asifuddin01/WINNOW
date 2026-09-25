import { useCallback, useState, type ReactNode } from "react";

import { Footer } from "@/components/layout/Footer";
import { DocumentTitle } from "@/components/layout/PageTitle";
import { SkipLink } from "@/components/layout/SkipLink";
import { AppSidebar } from "@/components/layout/AppSidebar";
import { CommandPalette } from "@/components/layout/CommandPalette";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { TopBar } from "@/components/layout/TopBar";
import { VerifyEmailBanner } from "@/components/layout/VerifyEmailBanner";
import { ShellContext } from "@/components/layout/shell-context";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { useCommandPalette } from "@/hooks/use-command-palette";
import { readPreference, writePreference } from "@/lib/storage";

const SIDEBAR_STORAGE_KEY = "winnow-sidebar";

/** Sidebar, top bar, page content and the footer, around every signed-in page. */
export function AppShell({ children }: { children: ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(
    () => readPreference(SIDEBAR_STORAGE_KEY) !== "collapsed",
  );
  const palette = useCommandPalette();
  const onSidebarOpenChange = useCallback((open: boolean) => {
    setSidebarOpen(open);
    writePreference(SIDEBAR_STORAGE_KEY, open ? "expanded" : "collapsed");
  }, []);

  return (
    <ShellContext value={true}>
      <SidebarProvider open={sidebarOpen} onOpenChange={onSidebarOpenChange}>
        <SkipLink />
        <DocumentTitle />
        <AppSidebar />
        <SidebarInset className="min-w-0">
          <TopBar
            onSearch={() => {
              palette.setOpen(true);
            }}
          />
          <StatusBanner />
          <VerifyEmailBanner />
          <main id="main" tabIndex={-1} className="flex flex-1 flex-col outline-none">
            {children}
          </main>
          <Footer />
        </SidebarInset>
        <CommandPalette open={palette.open} onOpenChange={palette.setOpen} />
      </SidebarProvider>
    </ShellContext>
  );
}

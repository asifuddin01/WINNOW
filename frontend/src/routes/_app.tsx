import { Outlet, createFileRoute } from "@tanstack/react-router";

import { AppShell } from "@/components/layout/AppShell";
import { ErrorPage } from "@/components/layout/ErrorPage";

/** Pathless layout: everything under it gets the sidebar, top bar and footer. */
export const Route = createFileRoute("/_app")({
  component: AppLayout,
  // An error in the layout itself renders outside the shell, as a standalone page.
  errorComponent: ErrorPage,
});

function AppLayout() {
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}

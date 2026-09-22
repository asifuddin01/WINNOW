import { useQuery } from "@tanstack/react-query";
import { Outlet, createFileRoute, redirect, useRouter } from "@tanstack/react-router";
import { useEffect } from "react";

import { loadMe, meQuery, safeRedirect } from "@/api/auth";
import { AppShell } from "@/components/layout/AppShell";
import { ErrorPage } from "@/components/layout/ErrorPage";

/** Pathless layout: everything under it needs a signed-in user and gets the app shell. */
export const Route = createFileRoute("/_app")({
  beforeLoad: async ({ context, location }) => {
    const me = await loadMe(context.queryClient);
    if (!me) redirect({ to: "/login", search: { redirect: location.href }, throw: true });
  },
  component: AppLayout,
  // An error in the layout itself renders outside the shell, as a standalone page.
  errorComponent: ErrorPage,
});

/**
 * The session can end while a page is open (it expired, or you signed out elsewhere).
 * Go to sign-in once, remembering where you were, but never "back" to a sign-in page:
 * reading the location mid-navigation would otherwise nest redirects without end.
 */
function useLeaveWhenSignedOut(): void {
  const { data: me } = useQuery(meQuery);
  const router = useRouter();
  useEffect(() => {
    if (me !== null) return;
    const here = router.state.location.href;
    const back = safeRedirect(here);
    void router.navigate({
      to: "/login",
      search: back === "/" ? {} : { redirect: back },
      replace: true,
    });
  }, [me, router]);
}

function AppLayout() {
  useLeaveWhenSignedOut();
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}

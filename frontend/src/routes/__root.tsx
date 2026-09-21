import type { QueryClient } from "@tanstack/react-query";
import { Outlet, createRootRouteWithContext } from "@tanstack/react-router";

import { ErrorPage } from "@/components/layout/ErrorPage";
import { NotFoundPage } from "@/components/layout/NotFoundPage";

export interface RouterContext {
  queryClient: QueryClient;
}

/**
 * The root renders no chrome: pages inside the app use the `_app` layout (sidebar,
 * top bar, footer); pages outside it (errors, not found, later sign-in) use
 * StandalonePage. Both render the footer.
 */
export const Route = createRootRouteWithContext<RouterContext>()({
  component: Outlet,
  errorComponent: ErrorPage,
  notFoundComponent: NotFoundPage,
});

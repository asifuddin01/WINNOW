import type { QueryClient } from "@tanstack/react-query";
import { createRouter, type RouterHistory } from "@tanstack/react-router";

import { ErrorPage } from "@/components/layout/ErrorPage";
import { NotFoundPage } from "@/components/layout/NotFoundPage";
import { routeTree } from "@/routeTree.gen";

export function createAppRouter(queryClient: QueryClient, history?: RouterHistory) {
  return createRouter({
    routeTree,
    context: { queryClient },
    ...(history && { history }),
    // Load a route's code and data when a link is hovered or focused (guide 11.5).
    defaultPreload: "intent",
    // TanStack Query owns caching; the router always asks it.
    defaultPreloadStaleTime: 0,
    scrollRestoration: true,
    defaultErrorComponent: ErrorPage,
    defaultNotFoundComponent: NotFoundPage,
  });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}

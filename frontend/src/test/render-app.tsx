import { createMemoryHistory } from "@tanstack/react-router";
import { render } from "@testing-library/react";

import { App } from "@/App";
import { createQueryClient } from "@/lib/query-client";
import { createAppRouter } from "@/router";

/** The real app (routes, providers, shell) on an in-memory URL. */
export function renderApp(path = "/") {
  const queryClient = createQueryClient();
  const router = createAppRouter(queryClient, createMemoryHistory({ initialEntries: [path] }));
  const view = render(<App router={router} queryClient={queryClient} />);
  return { ...view, router, queryClient };
}

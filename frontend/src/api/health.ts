import { queryOptions } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";

/** Whether the API can reach its database and Redis. Polled for the status banner. */
export const readinessQuery = queryOptions({
  queryKey: ["health", "readiness"],
  queryFn: async ({ signal }) => unwrap(await api.GET("/api/v1/readyz", { signal })),
  refetchInterval: 60_000,
  retry: false,
});

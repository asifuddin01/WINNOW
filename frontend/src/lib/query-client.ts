import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "@/api/client";

/** Client errors (4xx) will not fix themselves; retry only network and server failures. */
function shouldRetry(failureCount: number, error: Error): boolean {
  if (error instanceof ApiError && error.status < 500) return false;
  return failureCount < 2;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { staleTime: 30_000, retry: shouldRetry },
      mutations: { retry: false },
    },
  });
}

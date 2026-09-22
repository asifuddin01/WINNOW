import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";

import { authKeys } from "@/api/auth";
import { ApiError } from "@/api/client";
import { forgetCsrfToken } from "@/api/csrf";

/** Client errors (4xx) will not fix themselves; retry only network and server failures. */
function shouldRetry(failureCount: number, error: Error): boolean {
  if (error instanceof ApiError && error.status < 500) return false;
  return failureCount < 2;
}

export function createQueryClient(): QueryClient {
  // Any request that finds the session gone signs this tab out; the app layout then
  // sends the user to the sign-in page and back here afterwards.
  const onError = (error: Error) => {
    if (error instanceof ApiError && error.code === "not_authenticated") {
      forgetCsrfToken();
      queryClient.setQueryData(authKeys.me, null);
    }
  };
  const queryClient: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError }),
    mutationCache: new MutationCache({ onError }),
    defaultOptions: {
      queries: { staleTime: 30_000, retry: shouldRetry },
      mutations: { retry: false },
    },
  });
  return queryClient;
}

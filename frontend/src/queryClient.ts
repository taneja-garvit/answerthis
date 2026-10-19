import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "./api/client";

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        // Retry transient network failures once; never retry 4xx responses.
        retry: (failureCount, error) =>
          failureCount < 1 && error instanceof ApiError && (error.status === 0 || error.status >= 500),
      },
      mutations: { retry: false },
    },
  });
}

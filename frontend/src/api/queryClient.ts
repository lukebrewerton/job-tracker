// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { ApiError } from "./client";

/** Client errors (4xx) won't succeed on a retry; network and server errors might. */
function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status < 500) return false;
  return failureCount < 2;
}

function showError(error: unknown): void {
  // A 401 is already on its way to the sign-in page.
  if (error instanceof ApiError && error.status === 401) return;
  toast.error(error instanceof Error ? error.message : "Something went wrong");
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    // Errors are always surfaced, never swallowed.
    queryCache: new QueryCache({ onError: showError }),
    mutationCache: new MutationCache({ onError: showError }),
    defaultOptions: {
      queries: { retry: shouldRetry, staleTime: 30 * 1000 },
    },
  });
}

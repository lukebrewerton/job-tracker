// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { ApiError, navigation } from "./client";

/** Client errors (4xx) won't succeed on a retry; network and server errors might. */
function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status < 500) return false;
  return failureCount < 2;
}

/**
 * Per-query/mutation options, via `meta`:
 * - `silent`: never toast (e.g. a background check whose failure means nothing to the user);
 * - `inlineValidation`: the form shows 422 errors under its fields, so don't toast those;
 * - `expectedStatuses`: statuses the page handles itself (e.g. 404 → "Job not found").
 */
export interface ErrorMeta extends Record<string, unknown> {
  silent?: boolean;
  inlineValidation?: boolean;
  expectedStatuses?: number[];
}

function showError(error: unknown, meta: ErrorMeta | undefined): void {
  if (meta?.silent) return;
  // On the way to sign in, requests still in flight get cancelled: not errors to show.
  if (navigation.leaving) return;
  // A DOMException, which isn't an Error in every environment: check the name only.
  if (
    typeof error === "object" &&
    error !== null &&
    "name" in error &&
    error.name === "AbortError"
  ) {
    return;
  }
  if (error instanceof ApiError) {
    // A 401 is already on its way to the sign-in page.
    if (error.status === 401) return;
    if (error.status === 422 && meta?.inlineValidation) return;
    if (meta?.expectedStatuses?.includes(error.status)) return;
  }
  toast.error(error instanceof Error ? error.message : "Something went wrong");
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    // Errors are always surfaced, never swallowed.
    queryCache: new QueryCache({
      onError: (error, query) => showError(error, query.meta),
    }),
    mutationCache: new MutationCache({
      onError: (error, _variables, _context, mutation) =>
        showError(error, mutation.meta),
    }),
    defaultOptions: {
      queries: { retry: shouldRetry, staleTime: 30 * 1000 },
    },
  });
}

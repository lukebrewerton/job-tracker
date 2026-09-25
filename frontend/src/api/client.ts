// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// The typed API client. Every path, parameter and response is typed from
// ./schema.ts, which `make types` generates from the committed openapi.json.
import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "./schema";

/** Pages that work signed out: a 401 there means "signed out", not "go and sign in". */
export const PUBLIC_PATHS: ReadonlySet<string> = new Set(["/"]);

/** Full-page navigations, behind one object so tests can observe them. */
export const navigation = {
  assign(url: string): void {
    window.location.assign(url);
  },
};

/** Sign in, then come back to exactly this page (path and query). */
export function loginUrl(
  location: Pick<Location, "pathname" | "search">,
): string {
  return `/auth/login?next=${encodeURIComponent(location.pathname + location.search)}`;
}

const signInOn401: Middleware = {
  onResponse({ response }) {
    if (
      response.status === 401 &&
      !PUBLIC_PATHS.has(window.location.pathname)
    ) {
      navigation.assign(loginUrl(window.location));
    }
    return response;
  },
};

export const api = createClient<paths>({
  baseUrl: window.location.origin,
  // Looked up per call (not captured once), so tests can substitute fetch.
  fetch: (request) => globalThis.fetch(request),
});
api.use(signInOn401);

/** A failed API call, with its status and the error body the API returned. */
export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown) {
    super(errorMessage(status, body));
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

function errorMessage(status: number, body: unknown): string {
  if (body && typeof body === "object" && "detail" in body) {
    const { detail } = body;
    if (typeof detail === "string") return detail;
    // FastAPI validation errors: a list of {msg}.
    if (Array.isArray(detail) && detail.length > 0) {
      const first: unknown = detail[0];
      if (
        first &&
        typeof first === "object" &&
        "msg" in first &&
        typeof first.msg === "string"
      ) {
        return first.msg;
      }
    }
  }
  return `Request failed (${status})`;
}

/** The response body, or an ApiError: so TanStack Query sees failures as errors. */
export async function unwrap<T>(
  request: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await request;
  if (!response.ok || data === undefined)
    throw new ApiError(response.status, error);
  return data;
}

/** For responses with no body (204): success, or an ApiError. */
export async function expectNoContent(
  request: Promise<{ error?: unknown; response: Response }>,
): Promise<void> {
  const { error, response } = await request;
  if (!response.ok) throw new ApiError(response.status, error);
}

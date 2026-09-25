// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { vi } from "vitest";

import { routes } from "../routes";

export function testQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

/** Render the real routes at `path`, with a fresh query client. */
export function renderApp(path: string) {
  window.history.replaceState(null, "", path);
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const client = testQueryClient();
  return {
    client,
    router,
    ...render(
      <QueryClientProvider client={client}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    ),
  };
}

export function withQueryClient(ui: ReactNode, client = testQueryClient()) {
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

type Handler = (request: Request) => Response | Promise<Response>;

/** Replace fetch with a router of (method + path) → response, recording every request. */
export function mockApi(handlers: Record<string, Handler>) {
  const requests: Request[] = [];
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const request =
        input instanceof Request
          ? input
          : new Request(new URL(String(input), window.location.origin), init);
      requests.push(request);
      const key = `${request.method} ${new URL(request.url).pathname}`;
      const handler = handlers[key];
      if (!handler) throw new Error(`Unexpected request: ${key}`);
      return handler(request);
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return { requests, fetchMock };
}

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { afterEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";

import { ApiError, navigation } from "./client";
import { createQueryClient } from "./queryClient";

async function failWith(error: unknown, meta?: Record<string, unknown>) {
  const client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false } });
  await client
    .fetchQuery({
      queryKey: [Math.random()],
      queryFn: () => Promise.reject(error),
      meta,
    })
    .catch(() => {});
}

afterEach(() => {
  navigation.leaving = false;
});

describe("error toasts", () => {
  it("shows an API error's message", async () => {
    const shown = vi.spyOn(toast, "error");
    await failWith(new ApiError(500, { detail: "Database unavailable" }));
    expect(shown).toHaveBeenCalledWith("Database unavailable");
  });

  it("stays quiet for a cancelled request", async () => {
    const shown = vi.spyOn(toast, "error");
    await failWith(
      new DOMException("The operation was aborted.", "AbortError"),
    );
    expect(shown).not.toHaveBeenCalled();
  });

  it("stays quiet once the page is on its way to sign in", async () => {
    const shown = vi.spyOn(toast, "error");
    navigation.leaving = true;
    await failWith(new TypeError("Failed to fetch"));
    expect(shown).not.toHaveBeenCalled();
  });

  it("stays quiet for a 401, and for a query marked silent", async () => {
    const shown = vi.spyOn(toast, "error");
    await failWith(new ApiError(401, null));
    await failWith(new ApiError(422, null), { silent: true });
    expect(shown).not.toHaveBeenCalled();
  });
});

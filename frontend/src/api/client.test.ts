// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { afterEach, describe, expect, it, vi } from "vitest";

import { json, mockApi } from "../test/utils";
import { api, ApiError, loginUrl, navigation, unwrap } from "./client";

afterEach(() => vi.unstubAllGlobals());

describe("a 401 from the API", () => {
  it("sends you to sign in, then back to the exact path and query", async () => {
    window.history.replaceState(null, "", "/jobs?status=all&q=acme%20ltd");
    mockApi({
      "GET /api/jobs": () => json({ detail: "Not authenticated" }, 401),
    });
    const assign = vi.spyOn(navigation, "assign").mockImplementation(() => {});

    await api.GET("/api/jobs", {});

    expect(assign).toHaveBeenCalledWith(
      `/auth/login?next=${encodeURIComponent("/jobs?status=all&q=acme%20ltd")}`,
    );
  });

  it("doesn't redirect on the public front page, where it just means signed out", async () => {
    window.history.replaceState(null, "", "/");
    mockApi({
      "GET /api/me": () => json({ detail: "Not authenticated" }, 401),
    });
    const assign = vi.spyOn(navigation, "assign").mockImplementation(() => {});

    await api.GET("/api/me");

    expect(assign).not.toHaveBeenCalled();
  });

  it("isn't triggered by other errors", async () => {
    window.history.replaceState(null, "", "/jobs");
    mockApi({ "GET /api/jobs": () => json({ detail: "Nope" }, 403) });
    const assign = vi.spyOn(navigation, "assign").mockImplementation(() => {});

    await api.GET("/api/jobs", {});

    expect(assign).not.toHaveBeenCalled();
  });
});

describe("loginUrl", () => {
  it("encodes the path and query as one `next` value", () => {
    expect(
      loginUrl({
        pathname: "/jobs/new",
        search: "?url=https%3A%2F%2Fx.test&title=A%20B",
      }),
    ).toBe(
      "/auth/login?next=%2Fjobs%2Fnew%3Furl%3Dhttps%253A%252F%252Fx.test%26title%3DA%2520B",
    );
  });
});

describe("unwrap", () => {
  it("returns the data of a successful response", async () => {
    mockApi({
      "GET /api/me": () => json({ email: "a@b.test", timezone: "UTC" }),
    });
    await expect(unwrap(api.GET("/api/me"))).resolves.toEqual({
      email: "a@b.test",
      timezone: "UTC",
    });
  });

  it("throws an ApiError carrying the API's message", async () => {
    window.history.replaceState(null, "", "/jobs");
    mockApi({
      "GET /api/jobs": () =>
        json(
          {
            detail: [
              { loc: ["query", "q"], msg: "Enter at least 2 characters" },
            ],
          },
          422,
        ),
    });
    const error = await unwrap(
      api.GET("/api/jobs", { params: { query: { q: "a" } } }),
    ).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 422,
      message: "Enter at least 2 characters",
    });
  });
});

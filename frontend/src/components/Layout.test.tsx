// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { navigation } from "../api/client";
import { json, mockApi, renderApp } from "../test/utils";

const ME = { email: "luke@example.test", timezone: "Europe/London" };

afterEach(() => vi.unstubAllGlobals());

/** Make the browser report `timeZone`, as Intl.DateTimeFormat does. */
function browserZone(timeZone: string) {
  const real = new Intl.DateTimeFormat().resolvedOptions();
  vi.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions").mockReturnValue({
    ...real,
    timeZone,
  });
}

function signedIn(extra: Parameters<typeof mockApi>[0] = {}) {
  browserZone("Europe/London");
  return mockApi({ "GET /api/me": () => json(ME), ...extra });
}

describe("the header, signed in", () => {
  it("shows the navigation, New job, your email and Log out", async () => {
    signedIn();
    renderApp("/dashboard");
    const header = screen.getByRole("banner");
    await within(header).findByText(ME.email);
    const main = within(header).getAllByRole("navigation", {
      name: "Main",
    })[0]!;
    expect(
      within(main)
        .getAllByRole("link")
        .map((a) => a.textContent),
    ).toEqual(["Dashboard", "Jobs", "Interviews"]);
    expect(
      within(header).getByRole("link", { name: "New job" }),
    ).toHaveAttribute("href", "/jobs/new");
    expect(
      within(header).getByRole("button", { name: "Log out" }),
    ).toBeInTheDocument();
  });

  it("has an accessible Menu button that opens and closes the mobile menu", async () => {
    signedIn();
    const user = userEvent.setup();
    renderApp("/dashboard");
    const button = await screen.findByRole("button", { name: /menu/i });
    expect(button).toHaveAttribute("aria-expanded", "false");

    await user.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    const panel = document.getElementById(
      button.getAttribute("aria-controls")!,
    );
    expect(panel).toBeInTheDocument();
    // Focus moves into the menu.
    expect(
      within(panel!).getByRole("link", { name: "Dashboard" }),
    ).toHaveFocus();

    await user.keyboard("{Escape}");
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveFocus();

    await user.click(button);
    await user.click(
      within(
        document.getElementById(button.getAttribute("aria-controls")!)!,
      ).getByRole("link", { name: "Jobs" }),
    );
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(
      await screen.findByRole("heading", { name: "Jobs" }),
    ).toBeInTheDocument();
  });

  it("logs out with a POST and lands on the front page", async () => {
    const { requests } = signedIn({
      "POST /auth/logout": () => new Response(null, { status: 204 }),
    });
    const assign = vi.spyOn(navigation, "assign").mockImplementation(() => {});
    const user = userEvent.setup();
    renderApp("/dashboard");

    const header = screen.getByRole("banner");
    await user.click(
      await within(header).findByRole("button", { name: "Log out" }),
    );

    await waitFor(() => expect(assign).toHaveBeenCalledWith("/?signed_out=1"));
    expect(
      requests.some(
        (r) => r.method === "POST" && r.url.endsWith("/auth/logout"),
      ),
    ).toBe(true);
  });
});

describe("time zone sync", () => {
  it("saves the browser's zone when it differs from the stored one", async () => {
    browserZone("America/New_York");
    const { requests } = mockApi({
      "GET /api/me": () => json(ME),
      "PUT /api/me/timezone": () => json({ timezone: "America/New_York" }),
    });
    renderApp("/dashboard");
    await waitFor(() =>
      expect(requests.some((r) => r.method === "PUT")).toBe(true),
    );
    const put = requests.find((r) => r.method === "PUT")!;
    await expect(put.json()).resolves.toEqual({ timezone: "America/New_York" });
  });

  it("does nothing when they match", async () => {
    const { requests } = signedIn();
    renderApp("/dashboard");
    await screen.findByText(ME.email);
    expect(requests.some((r) => r.method === "PUT")).toBe(false);
  });

  it("logs, and doesn't show, a zone the server rejects", async () => {
    browserZone("Mars/Olympus_Mons");
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    mockApi({
      "GET /api/me": () => json(ME),
      "PUT /api/me/timezone": () =>
        json({ detail: [{ msg: "Unknown time zone" }] }, 422),
    });
    renderApp("/dashboard");
    await waitFor(() => expect(warn).toHaveBeenCalled());
    expect(screen.queryByText(/unknown time zone/i)).not.toBeInTheDocument();
  });
});

describe("the front page", () => {
  it("offers Sign in when signed out, and says so after logging out", async () => {
    mockApi({
      "GET /api/me": () => json({ detail: "Not authenticated" }, 401),
    });
    const assign = vi.spyOn(navigation, "assign").mockImplementation(() => {});
    renderApp("/?signed_out=1");

    expect(await screen.findByText("You've signed out.")).toBeInTheDocument();
    const signIns = await screen.findAllByRole("link", { name: "Sign in" });
    for (const link of signIns) {
      expect(link).toHaveAttribute(
        "href",
        `/auth/login?next=${encodeURIComponent("/dashboard")}`,
      );
    }
    expect(
      screen.queryByRole("navigation", { name: "Main" }),
    ).not.toBeInTheDocument();
    expect(assign).not.toHaveBeenCalled(); // no bounce to the sign-in page
  });

  it("links to the pages when signed in", async () => {
    signedIn();
    renderApp("/");
    const goTo = await screen.findByRole("navigation", { name: "Go to" });
    expect(
      within(goTo)
        .getAllByRole("link")
        .map((a) => a.getAttribute("href")),
    ).toEqual(["/dashboard", "/jobs", "/interviews"]);
    expect(
      screen.getByText(ME.email, { selector: "span.font-medium" }),
    ).toBeInTheDocument();
  });
});

describe("routes", () => {
  it("shows a 404 page for an unknown address", async () => {
    signedIn();
    renderApp("/no/such/page");
    expect(
      await screen.findByRole("heading", { name: "Page not found" }),
    ).toBeInTheDocument();
  });

  it.each([
    ["/dashboard", "Dashboard"],
    ["/jobs", "Jobs"],
    ["/jobs/new", "New job"],
    ["/interviews", "Interviews"],
  ])("%s has its page", async (path, heading) => {
    signedIn();
    renderApp(path);
    expect(
      await screen.findByRole("heading", { name: heading }),
    ).toBeInTheDocument();
  });
});

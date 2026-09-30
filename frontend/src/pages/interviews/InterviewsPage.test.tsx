// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { InterviewGroups, InterviewWithJob } from "../../api/interviews";
import { json, mockApi, renderApp } from "../../test/utils";

const ME = { email: "luke@example.test", timezone: "Europe/London" };

function interview(
  overrides: Partial<InterviewWithJob> = {},
): InterviewWithJob {
  const jobId = crypto.randomUUID();
  return {
    id: crypto.randomUUID(),
    job_id: jobId,
    scheduled_at: null,
    mode: null,
    round_label: null,
    notes: null,
    created_at: "2026-09-10T09:00:00Z",
    job: {
      id: jobId,
      company: "Acme Ltd",
      role: "Platform Engineer",
      status: "interviewing",
    },
    ...overrides,
  };
}

function serve(groups: Partial<InterviewGroups> = {}) {
  return mockApi({
    "GET /api/v1/me": () => json(ME),
    "GET /api/v1/interviews": () =>
      json({ upcoming: [], not_yet_scheduled: [], past: [], ...groups }),
  });
}

const group = (name: RegExp | string) => screen.findByRole("region", { name });

/** The desktop table's rows (without the header) and the mobile cards. */
function layouts(region: HTMLElement) {
  const rows = within(within(region).getByRole("table"))
    .getAllByRole("row")
    .slice(1);
  const cards = within(within(region).getByRole("list")).getAllByRole(
    "listitem",
  );
  return { rows, cards };
}

beforeEach(() => {
  // Thu 1 Oct 2026, 10:00 in London; only Date, so userEvent's timers still run.
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-01T09:00:00Z"));
  const real = new Intl.DateTimeFormat().resolvedOptions();
  vi.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions").mockReturnValue({
    ...real,
    timeZone: ME.timezone,
  });
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("the interviews page", () => {
  it("lists upcoming interviews in the server's order, in both layouts", async () => {
    const today = interview({
      round_label: "Technical",
      scheduled_at: "2026-10-01T13:00:00Z",
      mode: "remote",
    });
    const tomorrow = interview({
      round_label: null,
      scheduled_at: "2026-10-02T08:30:00Z",
      job: {
        id: "0199aaaa-0000-7000-8000-000000000002",
        company: "Globex",
        role: "SRE",
        status: "applied",
      },
    });
    const later = interview({
      round_label: "Final",
      scheduled_at: "2026-10-08T13:00:00Z",
      mode: "in_person",
    });
    serve({ upcoming: [today, tomorrow, later] });
    renderApp("/interviews");

    const upcoming = await group("Upcoming (3)");
    const { rows, cards } = layouts(upcoming);
    for (const items of [rows, cards]) {
      expect(items).toHaveLength(3);
      expect(items[0]).toHaveTextContent("Technical");
      expect(items[0]).toHaveTextContent("Today, 14:00"); // 13:00 UTC = 14:00 BST
      expect(items[0]).toHaveTextContent("Remote");
      expect(items[1]).toHaveTextContent("Interview");
      expect(items[1]).toHaveTextContent("Tomorrow, 09:30");
      expect(items[1]).toHaveTextContent("Globex");
      expect(items[1]).toHaveTextContent("SRE");
      expect(items[1]).toHaveTextContent("Applied");
      expect(items[2]).toHaveTextContent("Thu 8 Oct 2026, 14:00");
      expect(items[2]).toHaveTextContent("In person");
    }
  });

  it("links each interview to its job's interviews", async () => {
    const booked = interview({ scheduled_at: "2026-10-05T13:00:00Z" });
    serve({ upcoming: [booked] });
    renderApp("/interviews");
    const upcoming = await group("Upcoming (1)");
    const href = `/jobs/${booked.job.id}#interviews`;
    const { rows, cards } = layouts(upcoming);
    expect(
      within(rows[0]!).getByRole("link", { name: "Acme Ltd" }),
    ).toHaveAttribute("href", href);
    expect(within(cards[0]!).getByRole("link")).toHaveAttribute("href", href);
  });

  it("lists unscheduled interviews without a When column", async () => {
    serve({
      upcoming: [interview({ scheduled_at: "2026-10-05T13:00:00Z" })],
      not_yet_scheduled: [interview({ round_label: "Phone screen" })],
    });
    renderApp("/interviews");
    const unscheduled = await group("Not yet scheduled (1)");
    expect(
      within(unscheduled).queryByRole("columnheader", { name: "When" }),
    ).not.toBeInTheDocument();
    const { rows, cards } = layouts(unscheduled);
    expect(rows[0]).toHaveTextContent("Phone screen");
    expect(cards[0]).toHaveTextContent("Phone screen");
  });

  it("says None for an empty group, and leaves out Past when there are none", async () => {
    serve({ not_yet_scheduled: [interview()] });
    renderApp("/interviews");
    expect(
      within(await group("Upcoming (0)")).getByText("None."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: "Past" }),
    ).not.toBeInTheDocument();
  });

  it("collapses past interviews until opened", async () => {
    serve({
      past: [
        interview({
          round_label: "Final",
          scheduled_at: "2026-09-20T13:00:00Z",
        }),
      ],
    });
    const user = userEvent.setup();
    renderApp("/interviews");
    const past = await group("Past");
    const details = past.querySelector("details")!;
    expect(details).not.toHaveAttribute("open");

    await user.click(within(past).getByText("Past (1)"));
    expect(details).toHaveAttribute("open");
    expect(layouts(past).rows[0]).toHaveTextContent("Sun 20 Sept 2026, 14:00");
  });

  it("says so when there are no interviews at all", async () => {
    serve();
    renderApp("/interviews");
    expect(
      await screen.findByText("No interviews yet. Add them from a job's page."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to jobs" })).toHaveAttribute(
      "href",
      "/jobs",
    );
    expect(
      screen.queryByRole("region", { name: /Upcoming/ }),
    ).not.toBeInTheDocument();
  });
});

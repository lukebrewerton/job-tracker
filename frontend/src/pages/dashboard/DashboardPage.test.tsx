// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Toaster } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Dashboard, DashboardCounts, StaleJob } from "../../api/dashboard";
import type { InterviewWithJob } from "../../api/interviews";
import { json, mockApi, renderApp } from "../../test/utils";

const ME = { email: "luke@example.test", timezone: "Europe/London" };

const COUNTS: DashboardCounts = {
  active: 20,
  saved: 5,
  applied_ever: 30,
  interviewing: 3,
  offer: 1,
  rejected_at_application: 12,
  rejected_after_interview: 4,
  no_response: 6,
  withdrawn: 2,
  accepted: 1,
};

let n = 0;
function staleJob(overrides: Partial<StaleJob> = {}): StaleJob {
  n += 1;
  return {
    id: `0199aaaa-0000-7000-8000-${String(n).padStart(12, "0")}`,
    company: `Company ${n}`,
    role: "Platform Engineer",
    status: "applied",
    last_status_change_at: "2026-09-01T09:00:00Z",
    days_since_last_change: 20,
    ...overrides,
  };
}

function interview(
  overrides: Partial<InterviewWithJob> = {},
): InterviewWithJob {
  return {
    id: crypto.randomUUID(),
    job_id: "0199bbbb-0000-7000-8000-000000000001",
    scheduled_at: "2026-10-01T13:00:00Z",
    mode: "remote",
    round_label: "Technical",
    notes: null,
    created_at: "2026-09-10T09:00:00Z",
    job: {
      id: "0199bbbb-0000-7000-8000-000000000001",
      company: "Acme Ltd",
      role: "SRE",
      status: "interviewing",
    },
    ...overrides,
  };
}

function dashboard(overrides: Partial<Dashboard> = {}): Dashboard {
  return {
    counts: COUNTS,
    needs_follow_up: [],
    still_to_apply: [],
    no_response_candidates: [],
    upcoming_interviews: [],
    upcoming_interviews_total: 0,
    thresholds: { stale_after_days: 7, no_response_after_days: 14 },
    ...overrides,
  };
}

type Handlers = Parameters<typeof mockApi>[0];

/**
 * Serves the dashboard like the API: marking jobs as no response takes them off the
 * candidates list and moves them from active to no_response in the counts.
 */
function serve(initial: Partial<Dashboard> = {}, extra: Handlers = {}) {
  let state = dashboard(initial);
  const mark = (ids: string[]) => {
    const marked = state.no_response_candidates.filter((j) =>
      ids.includes(j.id),
    );
    state = {
      ...state,
      no_response_candidates: state.no_response_candidates.filter(
        (j) => !ids.includes(j.id),
      ),
      counts: {
        ...state.counts,
        active: state.counts.active - marked.length,
        no_response: state.counts.no_response + marked.length,
      },
    };
    return marked.map((j) => j.id);
  };
  const handlers: Handlers = {
    "GET /api/v1/me": () => json(ME),
    "GET /api/v1/dashboard": () => json(state),
    "POST /api/v1/jobs/bulk-status": async (request) => {
      const body: unknown = await request.json();
      const ids =
        body &&
        typeof body === "object" &&
        "ids" in body &&
        Array.isArray(body.ids)
          ? body.ids.map(String)
          : [];
      return json({ updated: mark(ids), unchanged: [], not_found: [] });
    },
    ...Object.fromEntries(
      (initial.no_response_candidates ?? []).map((job) => [
        `POST /api/v1/jobs/${job.id}/status`,
        () => {
          mark([job.id]);
          return json({ ...job, status: "no_response" });
        },
      ]),
    ),
    ...extra,
  };
  return { ...mockApi(handlers), mark };
}

const region = (name: RegExp | string) => screen.findByRole("region", { name });

beforeEach(() => {
  n = 0;
  // Thu 1 Oct 2026, 10:00 in London; only Date, so userEvent's timers still run.
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-01T09:00:00Z"));
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("the tiles", () => {
  it("show the counts, each linking to the jobs with that status", async () => {
    serve();
    renderApp("/dashboard");
    const tiles = await screen.findByRole("list", { name: "Counts" });
    const link = (name: RegExp) => within(tiles).getByRole("link", { name });
    expect(link(/^20 Active/)).toHaveAttribute("href", "/jobs?status=active");
    expect(link(/^5 Saved/)).toHaveAttribute("href", "/jobs?status=saved");
    expect(link(/^6 No response/)).toHaveAttribute(
      "href",
      "/jobs?status=no_response",
    );
    // Rejected: one tile, with its split.
    expect(link(/^16 Rejected/)).toHaveAttribute(
      "href",
      "/jobs?status=rejected",
    );
    expect(link(/^16 Rejected/)).toHaveTextContent(
      "12 at application · 4 after interview",
    );
    // Applied counts jobs whatever their status now: no filter matches, so no link.
    expect(within(tiles).getByText("Applied")).toBeInTheDocument();
    expect(
      within(tiles).queryByRole("link", { name: /Applied/ }),
    ).not.toBeInTheDocument();
  });

  it("give way to a prompt when there are no jobs at all", async () => {
    const none: DashboardCounts = {
      active: 0,
      saved: 0,
      applied_ever: 0,
      interviewing: 0,
      offer: 0,
      rejected_at_application: 0,
      rejected_after_interview: 0,
      no_response: 0,
      withdrawn: 0,
      accepted: 0,
    };
    serve({ counts: none });
    renderApp("/dashboard");
    expect(await screen.findByText("No jobs yet.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add a job" })).toHaveAttribute(
      "href",
      "/jobs/new",
    );
    expect(
      screen.queryByRole("list", { name: "Counts" }),
    ).not.toBeInTheDocument();
  });
});

describe("the lists", () => {
  it("show each job, how long it has waited, and a link to it", async () => {
    const job = staleJob({ company: "Globex", days_since_last_change: 9 });
    serve({ needs_follow_up: [job] });
    renderApp("/dashboard");
    const list = await region(/Needs follow-up \(1\)/);
    expect(list).toHaveTextContent("no movement for 7+ days");
    const link = within(list).getByRole("link", { name: /Globex/ });
    expect(link).toHaveAttribute("href", `/jobs/${job.id}`);
    expect(link).toHaveTextContent("9 days without movement");
    expect(
      within(await region(/Still to apply \(0\)/)).getByText(
        "Nothing waiting.",
      ),
    ).toBeInTheDocument();
  });

  it("show five, then all on request", async () => {
    serve({ still_to_apply: Array.from({ length: 7 }, () => staleJob()) });
    const user = userEvent.setup();
    renderApp("/dashboard");
    const list = await region(/Still to apply \(7\)/);
    expect(within(list).getAllByRole("listitem")).toHaveLength(5);
    await user.click(
      within(list).getByRole("button", { name: "Show all (7)" }),
    );
    expect(within(list).getAllByRole("listitem")).toHaveLength(7);
    await user.click(within(list).getByRole("button", { name: "Show fewer" }));
    expect(within(list).getAllByRole("listitem")).toHaveLength(5);
  });
});

describe("marking as no response", () => {
  it("removes the row at once, then updates the counts", async () => {
    const initech = staleJob({ company: "Initech" });
    let release!: () => void;
    const held = new Promise<void>((resolve) => (release = resolve));
    const api = serve(
      { no_response_candidates: [initech, staleJob()] },
      {
        // Held until released, to see the row go before the server answers.
        [`POST /api/v1/jobs/${initech.id}/status`]: async () => {
          await held;
          api.mark([initech.id]);
          return json({ ...initech, status: "no_response" });
        },
      },
    );
    const user = userEvent.setup();
    render(<Toaster />);
    renderApp("/dashboard");
    const list = await region(/No response\? \(2\)/);
    expect(list).toHaveTextContent("no movement for 14+ days");

    await user.click(
      within(list).getByRole("button", {
        name: "Mark Initech, Platform Engineer as no response",
      }),
    );
    await waitFor(() =>
      expect(within(list).getAllByRole("listitem")).toHaveLength(1),
    );
    const tiles = screen.getByRole("list", { name: "Counts" });
    expect(
      within(tiles).getByRole("link", { name: /^20 Active/ }),
    ).toBeInTheDocument(); // not yet

    release();
    expect(
      await screen.findByText("Marked Initech as no response"),
    ).toBeInTheDocument();
    // The counts follow, without a manual refresh.
    await waitFor(() =>
      expect(
        within(tiles).getByRole("link", { name: /^7 No response/ }),
      ).toBeInTheDocument(),
    );
    expect(
      within(tiles).getByRole("link", { name: /^19 Active/ }),
    ).toBeInTheDocument();
  });

  it("puts the row back, with a toast, when the change fails", async () => {
    const job = staleJob({ company: "Initech" });
    serve(
      { no_response_candidates: [job] },
      {
        [`POST /api/v1/jobs/${job.id}/status`]: () =>
          json({ detail: "Database unavailable" }, 500),
      },
    );
    const user = userEvent.setup();
    render(<Toaster />);
    renderApp("/dashboard");
    const list = await region(/No response\? \(1\)/);
    await user.click(
      within(list).getByRole("button", { name: /Mark Initech/ }),
    );
    expect(
      await screen.findByText("Couldn't mark Initech: Database unavailable"),
    ).toBeInTheDocument();
    expect(
      await within(list).findByRole("link", { name: /Initech/ }),
    ).toBeInTheDocument();
  });

  it("marks them all only after confirming, and just the ones shown", async () => {
    const jobs = [staleJob(), staleJob(), staleJob()];
    let sent: unknown;
    serve(
      { no_response_candidates: jobs },
      {
        "POST /api/v1/jobs/bulk-status": async (request) => {
          sent = await request.json();
          return json({
            updated: jobs.map((j) => j.id),
            unchanged: [],
            not_found: [],
          });
        },
      },
    );
    const user = userEvent.setup();
    render(<Toaster />);
    renderApp("/dashboard");
    const list = await region(/No response\? \(3\)/);
    await user.click(
      within(list).getByRole("button", { name: "Mark all as no response" }),
    );
    const dialog = screen.getByRole("dialog", {
      name: "Mark all as no response?",
    });
    expect(dialog).toHaveTextContent("Mark 3 jobs as no response?");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(sent).toBeUndefined();

    await user.click(
      within(list).getByRole("button", { name: "Mark all as no response" }),
    );
    await user.click(
      within(
        screen.getByRole("dialog", { name: "Mark all as no response?" }),
      ).getByRole("button", { name: "Mark 3 jobs" }),
    );
    await waitFor(() =>
      expect(sent).toEqual({
        ids: jobs.map((j) => j.id),
        status: "no_response",
      }),
    );
    expect(
      await screen.findByText("Marked 3 jobs as no response"),
    ).toBeInTheDocument();
  });
});

describe("upcoming interviews", () => {
  it("lists the next few, linking to each job, then to all of them", async () => {
    const next = interview();
    serve({ upcoming_interviews: [next], upcoming_interviews_total: 8 });
    renderApp("/dashboard");
    const panel = await region("Upcoming interviews");
    const link = within(panel).getByRole("link", { name: /Technical/ });
    expect(link).toHaveTextContent("Today, 14:00"); // 13:00 UTC = 14:00 BST
    expect(link).toHaveTextContent("Technical · Remote");
    expect(link).toHaveTextContent("Acme Ltd · SRE");
    expect(link).toHaveAttribute("href", `/jobs/${next.job.id}#interviews`);
    expect(
      within(panel).getByRole("link", { name: "View all (8)" }),
    ).toHaveAttribute("href", "/interviews");
  });

  it("says when there are none", async () => {
    serve();
    renderApp("/dashboard");
    const panel = await region("Upcoming interviews");
    expect(
      within(panel).getByText("No upcoming interviews."),
    ).toBeInTheDocument();
    expect(
      within(panel).getByRole("link", { name: "Go to interviews" }),
    ).toBeInTheDocument();
  });
});

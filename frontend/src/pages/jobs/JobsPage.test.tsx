// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Job, JobPage } from "../../api/jobs";
import { json, mockApi, renderApp } from "../../test/utils";
import {
  DEFAULT_VIEW,
  parseView,
  STORAGE_KEY,
  viewParams,
} from "./useJobsView";

const ME = { email: "luke@example.test", timezone: "Europe/London" };

function job(overrides: Partial<Job> = {}): Job {
  return {
    id: crypto.randomUUID(),
    company: "Acme Ltd",
    role: "Platform Engineer",
    url: null,
    location: null,
    source: null,
    salary: null,
    contact_name: null,
    contact_email: null,
    status: "applied",
    applied_at: "2026-09-10",
    notes: null,
    created_at: "2026-09-10T09:00:00Z",
    updated_at: "2026-09-10T09:00:00Z",
    last_status_change_at: "2026-09-10T09:00:00Z",
    days_since_last_change: 3,
    attention: null,
    ...overrides,
  };
}

const COUNTS: JobPage["counts"] = {
  saved: 1,
  applied: 2,
  interviewing: 1,
  offer: 0,
  accepted: 0,
  rejected: 3,
  withdrawn: 0,
  no_response: 1,
};

function page(items: Job[], overrides: Partial<JobPage> = {}): JobPage {
  return {
    items,
    total: items.length,
    page: 1,
    page_size: 25,
    counts: COUNTS,
    ...overrides,
  };
}

/** Serve `/api/jobs` from `respond`, recording each request's query. */
function serveJobs(
  respond: (query: URLSearchParams) => JobPage = () => page([job()]),
) {
  const queries: URLSearchParams[] = [];
  mockApi({
    "GET /api/me": () => json(ME),
    "GET /api/jobs": (request) => {
      const query = new URL(request.url).searchParams;
      queries.push(query);
      return json(respond(query));
    },
  });
  return queries;
}

const lastQuery = (queries: URLSearchParams[]) =>
  Object.fromEntries(queries.at(-1) ?? []);

beforeEach(() => {
  window.localStorage.clear();
  const real = new Intl.DateTimeFormat().resolvedOptions();
  vi.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions").mockReturnValue({
    ...real,
    timeZone: ME.timezone,
  });
});
afterEach(() => vi.unstubAllGlobals());

describe("the view in the URL", () => {
  it("leaves defaults out, and reads back what it writes", () => {
    expect(viewParams(DEFAULT_VIEW).toString()).toBe("");
    const view = {
      ...DEFAULT_VIEW,
      status: "rejected",
      q: "acme",
      sort: "company",
      order: "asc",
      size: 50,
      page: 3,
    } as const;
    expect(parseView(viewParams(view))).toEqual(view);
  });

  it("ignores invalid values", () => {
    const params = new URLSearchParams(
      "status=ghosted&sort=salary&order=up&size=10&page=-2",
    );
    expect(parseView(params)).toEqual(DEFAULT_VIEW);
  });
});

describe("the jobs page", () => {
  it("lists jobs, with the default view sent to the API", async () => {
    const queries = serveJobs(() =>
      page([job({ company: "Acme Ltd" }), job({ company: "Globex" })]),
    );
    renderApp("/jobs");
    const table = await screen.findByRole("table");
    expect(within(table).getByText("Acme Ltd")).toBeInTheDocument();
    expect(within(table).getByText("Globex")).toBeInTheDocument();
    expect(lastQuery(queries)).toMatchObject({
      status: "active",
      sort: "created_at",
      order: "desc",
      page: "1",
      page_size: "25",
    });
    expect(screen.getByText("Showing 1–2 of 2")).toBeInTheDocument();
  });

  it("shows each filter's count, and filters on click", async () => {
    const queries = serveJobs();
    const user = userEvent.setup();
    const { router } = renderApp("/jobs");
    const filters = await screen.findByRole("group", {
      name: "Filter by status",
    });
    const active = within(filters).getByRole("button", { name: /^Active/ });
    expect(active).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(active).toHaveTextContent("4")); // saved 1 + applied 2 + interviewing 1 + offer 0
    expect(
      within(filters).getByRole("button", { name: /^All/ }),
    ).toHaveTextContent("8");

    await user.click(
      within(filters).getByRole("button", { name: /^Rejected/ }),
    );
    await waitFor(() => expect(lastQuery(queries).status).toBe("rejected"));
    expect(router.state.location.search).toBe("?status=rejected");
  });

  it("highlights jobs that need attention, with a text label", async () => {
    serveJobs(() =>
      page([
        job({ company: "Chase me", attention: "needs_follow_up" }),
        job({
          company: "Write CV",
          status: "saved",
          applied_at: null,
          attention: "still_to_apply",
        }),
        job({ company: "Silent", attention: "no_response" }),
        job({ company: "Fine" }),
      ]),
    );
    renderApp("/jobs");
    const table = await screen.findByRole("table");
    const rowOf = (company: string) =>
      within(table).getByText(company).closest("tr")!;
    expect(
      within(rowOf("Chase me")).getByText("Follow up"),
    ).toBeInTheDocument();
    expect(
      within(rowOf("Write CV")).getByText("Still to apply"),
    ).toBeInTheDocument();
    expect(
      within(rowOf("Silent")).getByText("No response?"),
    ).toBeInTheDocument();
    expect(rowOf("Chase me").className).toMatch(/bg-amber-50/);
    expect(rowOf("Fine").className).not.toMatch(/bg-(amber|sky|rose)-50/);
  });

  it("sorts by a column header, and reverses on a second click", async () => {
    const queries = serveJobs();
    const user = userEvent.setup();
    renderApp("/jobs");
    const header = await screen.findByRole("columnheader", { name: /Company/ });
    expect(header).toHaveAttribute("aria-sort", "none");

    await user.click(within(header).getByRole("button"));
    await waitFor(() =>
      expect(lastQuery(queries)).toMatchObject({
        sort: "company",
        order: "asc",
      }),
    );
    expect(
      screen.getByRole("columnheader", { name: /Company/ }),
    ).toHaveAttribute("aria-sort", "ascending");

    await user.click(
      within(screen.getByRole("columnheader", { name: /Company/ })).getByRole(
        "button",
      ),
    );
    await waitFor(() =>
      expect(lastQuery(queries)).toMatchObject({
        sort: "company",
        order: "desc",
      }),
    );
  });

  it("can sort by the default column both ways (a saved view doesn't snap back)", async () => {
    const queries = serveJobs();
    const user = userEvent.setup();
    const { router } = renderApp("/jobs");
    const header = () => screen.getByRole("columnheader", { name: /Added/ });
    await screen.findByRole("table");

    await user.click(within(header()).getByRole("button")); // oldest first
    await waitFor(() =>
      expect(lastQuery(queries)).toMatchObject({
        sort: "created_at",
        order: "asc",
      }),
    );
    await waitFor(() =>
      expect(window.localStorage.getItem(STORAGE_KEY)).toBe("order=asc"),
    );

    // Back to newest first, the defaults. (The rows come from the cache, so this is
    // checked on screen and in the URL rather than as a new request.)
    await user.click(within(header()).getByRole("button"));
    await waitFor(() =>
      expect(header()).toHaveAttribute("aria-sort", "descending"),
    );
    expect(router.state.location.search).toBe("");
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
    await new Promise((r) => setTimeout(r, 50)); // would it snap back? it mustn't
    expect(header()).toHaveAttribute("aria-sort", "descending");
    expect(router.state.location.search).toBe("");
  });

  it("can go back to the Active filter after trying another", async () => {
    const queries = serveJobs();
    const user = userEvent.setup();
    const { router } = renderApp("/jobs");
    const filters = await screen.findByRole("group", {
      name: "Filter by status",
    });
    const button = (name: RegExp) =>
      within(filters).getByRole("button", { name });
    await user.click(button(/^Rejected/));
    await waitFor(() => expect(lastQuery(queries).status).toBe("rejected"));

    await user.click(button(/^Active/));
    await waitFor(() =>
      expect(button(/^Active/)).toHaveAttribute("aria-pressed", "true"),
    );
    await new Promise((r) => setTimeout(r, 50)); // would it snap back? it mustn't
    expect(button(/^Active/)).toHaveAttribute("aria-pressed", "true");
    expect(router.state.location.search).toBe("");
  });

  it("offers the filters as one dropdown on small screens, with counts", async () => {
    const queries = serveJobs();
    const user = userEvent.setup();
    renderApp("/jobs");
    const select = await screen.findByRole("combobox", { name: "Status" });
    await waitFor(() =>
      expect(
        within(select).getByRole("option", { name: "Active (4)" }),
      ).toBeInTheDocument(),
    );
    expect(
      within(select).getByRole("option", { name: "Rejected (3)" }),
    ).toBeInTheDocument();
    await user.selectOptions(select, "rejected");
    await waitFor(() => expect(lastQuery(queries).status).toBe("rejected"));
  });

  it("searches after a pause, and asks for 2 characters first", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const queries = serveJobs();
      const user = userEvent.setup({
        advanceTimers: vi.advanceTimersByTime.bind(vi),
      });
      renderApp("/jobs");
      const box = await screen.findByRole("searchbox", {
        name: "Search company or role",
      });

      await user.type(box, "a");
      expect(
        screen.getByText("Enter at least 2 characters"),
      ).toBeInTheDocument();
      await act(() => vi.advanceTimersByTimeAsync(1000));
      expect(queries.every((q) => !q.has("q"))).toBe(true);

      await user.type(box, "c");
      expect(
        screen.queryByText("Enter at least 2 characters"),
      ).not.toBeInTheDocument();
      await act(() => vi.advanceTimersByTimeAsync(300));
      await waitFor(() => expect(lastQuery(queries).q).toBe("ac"));
    } finally {
      vi.useRealTimers();
    }
  });

  it("pages through results, and says how many there are", async () => {
    const queries = serveJobs((q) =>
      page(
        Array.from({ length: 25 }, (_, i) => job({ company: `Company ${i}` })),
        { total: 57, page: Number(q.get("page")), page_size: 25 },
      ),
    );
    const user = userEvent.setup();
    renderApp("/jobs");
    expect(await screen.findByText("Showing 1–25 of 57")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(lastQuery(queries).page).toBe("2"));
    expect(await screen.findByText("Showing 26–50 of 57")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Per page"), "50");
    await waitFor(() =>
      expect(lastQuery(queries)).toMatchObject({ page_size: "50", page: "1" }),
    );
  });

  it("restores the saved view on a bare /jobs, but not the page number", async () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      "status=all&sort=company&order=asc",
    );
    const queries = serveJobs();
    const { router } = renderApp("/jobs");
    await screen.findByRole("table");
    // The very first request already uses the saved view: no flash of the defaults.
    expect(Object.fromEntries(queries[0]!)).toMatchObject({
      status: "all",
      sort: "company",
      order: "asc",
      page: "1",
    });
    await waitFor(() =>
      expect(router.state.location.search).toBe(
        "?status=all&sort=company&order=asc",
      ),
    );
  });

  it("saves the view (without the page) as it changes", async () => {
    serveJobs();
    const user = userEvent.setup();
    renderApp("/jobs?page=3");
    const filters = await screen.findByRole("group", {
      name: "Filter by status",
    });
    await user.click(within(filters).getByRole("button", { name: /^All/ }));
    await waitFor(() =>
      expect(window.localStorage.getItem(STORAGE_KEY)).toBe("status=all"),
    );
  });

  it("resets everything with Reset", async () => {
    window.localStorage.setItem(STORAGE_KEY, "status=all&q=acme");
    const queries = serveJobs();
    const user = userEvent.setup();
    const { router } = renderApp("/jobs?status=all&q=acme");
    await user.click(await screen.findByRole("button", { name: "Reset" }));
    await waitFor(() => expect(router.state.location.search).toBe(""));
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
    expect(screen.getByRole("searchbox")).toHaveValue("");
    await waitFor(() => expect(lastQuery(queries).status).toBe("active"));
  });

  it("works when storage is unavailable, as in some private windows", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    serveJobs();
    const user = userEvent.setup();
    renderApp("/jobs");
    expect(await screen.findByRole("table")).toBeInTheDocument();
    const filters = screen.getByRole("group", { name: "Filter by status" });
    await user.click(within(filters).getByRole("button", { name: /^All/ }));
    expect(await screen.findByRole("table")).toBeInTheDocument();
  });

  it("offers to add a job when there are none", async () => {
    const none: JobPage["counts"] = {
      saved: 0,
      applied: 0,
      interviewing: 0,
      offer: 0,
      accepted: 0,
      rejected: 0,
      withdrawn: 0,
      no_response: 0,
    };
    serveJobs(() => ({ ...page([]), counts: none }));
    renderApp("/jobs");
    expect(await screen.findByText("No jobs yet.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add a job" })).toHaveAttribute(
      "href",
      "/jobs/new",
    );
  });

  it("offers Reset when nothing matches", async () => {
    serveJobs(() => page([]));
    renderApp("/jobs?status=offer");
    expect(await screen.findByText("No jobs match.")).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: "Reset" }).length,
    ).toBeGreaterThan(0);
  });

  it("links each job to its page, as a row and as a card", async () => {
    const acme = job({ company: "Acme Ltd" });
    serveJobs(() => page([acme]));
    renderApp("/jobs");
    const links = await screen.findAllByRole("link", { name: /Acme Ltd/ });
    expect(links.length).toBe(2); // the table row's and the mobile card's
    for (const link of links)
      expect(link).toHaveAttribute("href", `/jobs/${acme.id}`);
  });
});

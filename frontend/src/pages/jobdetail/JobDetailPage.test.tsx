// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Toaster } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Job } from "../../api/jobs";
import { json, mockApi, renderApp } from "../../test/utils";

const ME = { email: "luke@example.test", timezone: "Europe/London" };
const ID = "0199aaaa-0000-7000-8000-000000000001";

function job(overrides: Partial<Job> = {}): Job {
  return {
    id: ID,
    company: "Acme Ltd",
    role: "Platform Engineer",
    url: "https://careers.acme.test/jobs/42",
    location: "London",
    source: "company_site",
    salary: null,
    contact_name: null,
    contact_email: null,
    status: "applied",
    applied_at: "2026-09-10",
    notes: null,
    created_at: "2026-09-01T09:00:00Z",
    updated_at: "2026-09-10T09:00:00Z",
    last_status_change_at: "2026-09-10T09:00:00Z",
    days_since_last_change: 9,
    attention: "needs_follow_up",
    ...overrides,
  };
}

const HISTORY = [
  { status: "applied", changed_at: "2026-09-10T09:00:00Z" },
  { status: "saved", changed_at: "2026-09-01T09:00:00Z" },
];

type Handlers = Parameters<typeof mockApi>[0];

function serve(extra: Handlers = {}) {
  return mockApi({
    "GET /api/me": () => json(ME),
    [`GET /api/jobs/${ID}`]: () => json(job()),
    [`GET /api/jobs/${ID}/history`]: () => json(HISTORY),
    [`GET /api/jobs/${ID}/interviews`]: () => json([{}, {}]),
    "GET /api/jobs": () =>
      json({ items: [], total: 0, page: 1, page_size: 25, counts: {} }),
    ...extra,
  });
}

beforeEach(() => {
  const real = new Intl.DateTimeFormat().resolvedOptions();
  vi.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions").mockReturnValue({
    ...real,
    timeZone: ME.timezone,
  });
});
afterEach(() => vi.unstubAllGlobals());

describe("the job page", () => {
  it("shows the job, its details and its history", async () => {
    serve();
    renderApp(`/jobs/${ID}`);
    expect(
      await screen.findByRole("heading", { name: "Acme Ltd" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Platform Engineer", { selector: "p" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Follow up")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /View job posting/ }),
    ).toHaveAttribute("href", "https://careers.acme.test/jobs/42");
    expect(screen.getByLabelText("Company *")).toHaveValue("Acme Ltd");
    expect(screen.getByLabelText("Location")).toHaveValue("London");
    expect(screen.getByLabelText("Applied on")).toHaveValue("2026-09-10");
    const history = await screen.findByRole("list");
    expect(within(history).getAllByRole("listitem")).toHaveLength(2);
  });

  it("says Job not found for a missing job, without an error toast", async () => {
    serve({
      [`GET /api/jobs/${ID}`]: () => json({ detail: "Job not found" }, 404),
    });
    render(<Toaster />);
    renderApp(`/jobs/${ID}`);
    expect(
      await screen.findByRole("heading", { name: "Job not found" }),
    ).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryAllByText("Job not found")).toHaveLength(1); // the heading only
  });

  it("hides the applied date for a saved job", async () => {
    serve({
      [`GET /api/jobs/${ID}`]: () =>
        json(job({ status: "saved", applied_at: null })),
    });
    renderApp(`/jobs/${ID}`);
    await screen.findByLabelText("Company *");
    expect(screen.queryByLabelText("Applied on")).not.toBeInTheDocument();
  });
});

describe("changing the status", () => {
  it("shows the new status straight away, then refreshes the history", async () => {
    let finish!: () => void;
    const { requests } = serve({
      [`POST /api/jobs/${ID}/status`]: () =>
        new Promise((resolve) => {
          finish = () =>
            resolve(
              json(
                job({
                  status: "interviewing",
                  attention: null,
                  days_since_last_change: 0,
                }),
              ),
            );
        }),
    });
    const user = userEvent.setup();
    renderApp(`/jobs/${ID}`);
    const picker = await screen.findByLabelText("Status");
    await user.selectOptions(picker, "interviewing");

    // Optimistic: the page header shows it before the server has answered.
    const header = document.querySelector<HTMLElement>("article header")!;
    await waitFor(() =>
      expect(within(header).getByText("Interviewing")).toBeInTheDocument(),
    );
    expect(picker).toHaveValue("interviewing");

    finish();
    await waitFor(() =>
      expect(
        requests.filter((r) => r.url.endsWith("/history")).length,
      ).toBeGreaterThan(1),
    );
  });

  it("rolls back visibly, with a toast, when the change fails", async () => {
    serve({
      [`POST /api/jobs/${ID}/status`]: () =>
        json({ detail: "Database unavailable" }, 500),
    });
    const user = userEvent.setup();
    render(<Toaster />);
    renderApp(`/jobs/${ID}`);
    const picker = await screen.findByLabelText("Status");
    await user.selectOptions(picker, "offer");

    expect(
      await screen.findByText(
        "Couldn't change the status: Database unavailable",
      ),
    ).toBeInTheDocument();
    await waitFor(() => expect(picker).toHaveValue("applied"));
  });
});

describe("editing the details", () => {
  it("offers Save only when something changed, and sends just the changes", async () => {
    let sent: unknown;
    serve({
      [`PATCH /api/jobs/${ID}`]: async (request) => {
        sent = await request.json();
        return json(job({ location: "Remote", salary: "£80k" }));
      },
    });
    const user = userEvent.setup();
    renderApp(`/jobs/${ID}`);
    const location = await screen.findByLabelText("Location");
    expect(
      screen.queryByRole("button", { name: "Save changes" }),
    ).not.toBeInTheDocument();

    await user.clear(location);
    await user.type(location, "Remote");
    await user.type(screen.getByLabelText("Salary"), "£80k");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(sent).toEqual({ location: "Remote", salary: "£80k" }),
    );
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Save changes" }),
      ).not.toBeInTheDocument(),
    );
    expect(screen.getByLabelText("Location")).toHaveValue("Remote");
  });

  it("clears an optional field with null, and Discard puts things back", async () => {
    serve();
    const user = userEvent.setup();
    renderApp(`/jobs/${ID}`);
    const location = await screen.findByLabelText("Location");
    await user.clear(location);
    expect(screen.getByText("You have unsaved changes")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Discard" }));
    expect(location).toHaveValue("London");
    expect(
      screen.queryByText("You have unsaved changes"),
    ).not.toBeInTheDocument();
  });

  it("shows validation errors under their fields", async () => {
    serve({
      [`PATCH /api/jobs/${ID}`]: () =>
        json(
          {
            detail: [
              {
                loc: ["body", "url"],
                msg: "URL must start with http:// or https://",
              },
            ],
          },
          422,
        ),
    });
    const user = userEvent.setup();
    renderApp(`/jobs/${ID}`);
    const url = await screen.findByLabelText("Job URL");
    await user.clear(url);
    await user.type(url, "careers.acme.test");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(url).toHaveAccessibleDescription(
        "URL must start with http:// or https://",
      ),
    );
  });

  it("says when the new URL is another job's", async () => {
    serve({
      [`PATCH /api/jobs/${ID}`]: () =>
        json(
          {
            detail: "Already tracked",
            existing_id: "0199bbbb-0000-7000-8000-000000000002",
          },
          409,
        ),
    });
    const user = userEvent.setup();
    renderApp(`/jobs/${ID}`);
    const url = await screen.findByLabelText("Job URL");
    await user.clear(url);
    await user.type(url, "https://careers.acme.test/jobs/7");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(
      await screen.findByText("Another job already has this URL"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View that job" })).toHaveAttribute(
      "href",
      "/jobs/0199bbbb-0000-7000-8000-000000000002",
    );
  });

  it("asks before leaving with unsaved changes", async () => {
    serve();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const user = userEvent.setup();
    const { router } = renderApp(`/jobs/${ID}`);
    await user.type(await screen.findByLabelText("Salary"), "£80k");
    await user.click(screen.getByRole("link", { name: "← Jobs" }));
    await waitFor(() =>
      expect(confirm).toHaveBeenCalledWith("Discard your changes?"),
    );
    expect(router.state.location.pathname).toBe(`/jobs/${ID}`); // stayed

    confirm.mockReturnValue(true);
    await user.click(screen.getByRole("link", { name: "← Jobs" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/jobs"));
  });
});

describe("deleting", () => {
  it("confirms, naming the job and what goes with it, then returns to the list", async () => {
    const { requests } = serve({
      [`DELETE /api/jobs/${ID}`]: () => new Response(null, { status: 204 }),
    });
    const user = userEvent.setup();
    render(<Toaster />);
    const { router } = renderApp(`/jobs/${ID}`);
    await user.click(await screen.findByRole("button", { name: "Delete job" }));

    const dialog = screen.getByRole("dialog", { name: "Delete this job?" });
    await waitFor(() =>
      expect(dialog).toHaveTextContent(
        "Delete Acme Ltd, Platform Engineer? Its status history and 2 interviews will be deleted too. This can't be undone.",
      ),
    );
    await user.click(
      within(dialog).getByRole("button", { name: "Delete job" }),
    );

    await waitFor(() => expect(router.state.location.pathname).toBe("/jobs"));
    expect(await screen.findByText("Job deleted")).toBeInTheDocument();
    expect(requests.some((r) => r.method === "DELETE")).toBe(true);
  });

  it("can be cancelled", async () => {
    const { requests } = serve();
    const user = userEvent.setup();
    renderApp(`/jobs/${ID}`);
    await user.click(await screen.findByRole("button", { name: "Delete job" }));
    const dialog = screen.getByRole("dialog", { name: "Delete this job?" });
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(requests.some((r) => r.method === "DELETE")).toBe(false);
  });
});

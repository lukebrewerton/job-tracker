// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster } from "sonner";
import { render } from "@testing-library/react";

import { json, mockApi, renderApp } from "../../test/utils";
import { navigation } from "../../api/client";
import { DRAFT_KEY, INTERRUPTED_KEY } from "./NewJobPage";

const ME = { email: "luke@example.test", timezone: "Europe/London" };
const EXTENSION_URL =
  "/jobs/new?url=https%3A%2F%2Fwww.linkedin.com%2Fjobs%2Fview%2F42&title=Platform%20Engineer%20-%20Acme%20%7C%20LinkedIn";

type Handlers = Parameters<typeof mockApi>[0];

function serve(extra: Handlers = {}) {
  return mockApi({
    "GET /api/me": () => json(ME),
    "GET /api/jobs/company-matches": () => json({ companies: [] }),
    ...extra,
  });
}

const createdJob = (body: Record<string, unknown>) => ({
  id: "0199aaaa-0000-7000-8000-000000000001",
  url: null,
  location: null,
  source: null,
  salary: null,
  contact_name: null,
  contact_email: null,
  applied_at: null,
  notes: null,
  status: "saved",
  created_at: "2026-09-25T12:00:00Z",
  updated_at: "2026-09-25T12:00:00Z",
  last_status_change_at: "2026-09-25T12:00:00Z",
  days_since_last_change: 0,
  attention: null,
  ...body,
});

beforeEach(() => {
  window.sessionStorage.clear();
  const real = new Intl.DateTimeFormat().resolvedOptions();
  vi.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions").mockReturnValue({
    ...real,
    timeZone: ME.timezone,
  });
});
afterEach(() => vi.unstubAllGlobals());

describe("pre-filling from the extension", () => {
  it("puts the raw title in Role, the URL in Job URL, and infers the source", async () => {
    serve();
    renderApp(EXTENSION_URL);
    expect(await screen.findByLabelText("Role *")).toHaveValue(
      "Platform Engineer - Acme | LinkedIn",
    );
    expect(screen.getByLabelText("Job URL")).toHaveValue(
      "https://www.linkedin.com/jobs/view/42",
    );
    expect(screen.getByLabelText("Source")).toHaveValue("linkedin");
    expect(screen.getByLabelText("Status")).toHaveValue("saved");
    expect(screen.getByLabelText("Company *")).toHaveValue("");
  });

  it("starts empty without parameters", async () => {
    serve();
    renderApp("/jobs/new");
    expect(await screen.findByLabelText("Role *")).toHaveValue("");
    expect(screen.getByLabelText("Source")).toHaveValue("");
  });
});

describe("the company warning", () => {
  it("lists matching companies as entered, with their statuses and links", async () => {
    serve({
      "GET /api/jobs/company-matches": (request) => {
        expect(new URL(request.url).searchParams.get("company")).toBe("acme");
        return json({
          companies: [
            {
              name: "Acme Ltd",
              total: 2,
              by_status: { applied: 1, no_response: 1 },
            },
            { name: "ACME", total: 1, by_status: { rejected: 1 } },
          ],
        });
      },
    });
    const user = userEvent.setup();
    renderApp("/jobs/new");
    await user.type(await screen.findByLabelText("Company *"), "acme");

    const warning = await screen.findByText(/You've tracked jobs at/);
    expect(warning).toHaveTextContent(
      "You've tracked jobs at Acme Ltd (2: 1 applied, 1 no response) and ACME (1: 1 rejected).",
    );
    expect(screen.getByRole("link", { name: "Acme Ltd" })).toHaveAttribute(
      "href",
      "/jobs?status=all&q=Acme+Ltd",
    );
  });

  it("stays silent (no warning, no error toast) while the input is too short to check", async () => {
    serve({
      "GET /api/jobs/company-matches": () =>
        json(
          {
            detail: [
              { loc: ["query", "company"], msg: "Enter at least 2 characters" },
            ],
          },
          422,
        ),
    });
    const user = userEvent.setup();
    render(<Toaster />);
    renderApp("/jobs/new");
    await user.type(await screen.findByLabelText("Company *"), "a Ltd");
    await new Promise((r) => setTimeout(r, 600));
    expect(screen.queryByText(/You've tracked/)).not.toBeInTheDocument();
    expect(
      screen.queryByText("Enter at least 2 characters"),
    ).not.toBeInTheDocument();
  });
});

describe("saving", () => {
  it("creates the job, then goes to its page", async () => {
    let sent: unknown;
    const { requests } = serve({
      "POST /api/jobs": async (request) => {
        sent = await request.json();
        return json(createdJob({ company: "Acme", role: "Engineer" }), 201);
      },
    });
    const user = userEvent.setup();
    const { router } = renderApp(EXTENSION_URL);
    await user.type(await screen.findByLabelText("Company *"), "Acme");
    await user.click(screen.getByRole("button", { name: "Save job" }));

    await waitFor(() =>
      expect(router.state.location.pathname).toBe(
        "/jobs/0199aaaa-0000-7000-8000-000000000001",
      ),
    );
    expect(sent).toMatchObject({
      company: "Acme",
      role: "Platform Engineer - Acme | LinkedIn",
      url: "https://www.linkedin.com/jobs/view/42",
      status: "saved",
      source: "linkedin",
      applied_at: null,
      location: null,
    });
    expect(requests.filter((r) => r.method === "POST")).toHaveLength(1);
    expect(window.sessionStorage.getItem(DRAFT_KEY)).toBeNull();
  });

  it("disables Save while saving", async () => {
    let finish!: () => void;
    serve({
      "POST /api/jobs": () =>
        new Promise((resolve) => {
          finish = () =>
            resolve(json(createdJob({ company: "Acme", role: "Eng" }), 201));
        }),
    });
    const user = userEvent.setup();
    renderApp("/jobs/new?title=Eng");
    await user.type(await screen.findByLabelText("Company *"), "Acme");
    await user.click(screen.getByRole("button", { name: "Save job" }));
    expect(
      await screen.findByRole("button", { name: "Saving…" }),
    ).toBeDisabled();
    finish();
  });

  it("shows Already tracked, with a link, for a duplicate URL", async () => {
    serve({
      "POST /api/jobs": () =>
        json(
          {
            detail: "Already tracked",
            existing_id: "0199bbbb-0000-7000-8000-000000000009",
          },
          409,
        ),
    });
    const user = userEvent.setup();
    const { router } = renderApp(EXTENSION_URL);
    await user.type(await screen.findByLabelText("Company *"), "Acme");
    await user.click(screen.getByRole("button", { name: "Save job" }));

    expect(await screen.findByText("Already tracked")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "View the existing job" }),
    ).toHaveAttribute("href", "/jobs/0199bbbb-0000-7000-8000-000000000009");
    expect(router.state.location.pathname).toBe("/jobs/new"); // what you typed is still here
    expect(screen.getByLabelText("Company *")).toHaveValue("Acme");
  });

  it("shows the server's validation message under its field", async () => {
    serve({
      "POST /api/jobs": () =>
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
    renderApp("/jobs/new?title=Eng&url=careers.acme.test");
    await user.type(await screen.findByLabelText("Company *"), "Acme");
    await user.click(screen.getByRole("button", { name: "Save job" }));

    const url = screen.getByLabelText("Job URL");
    await waitFor(() => expect(url).toHaveAttribute("aria-invalid", "true"));
    expect(url).toHaveAccessibleDescription(
      "URL must start with http:// or https://",
    );
  });

  it("only offers an applied date once the status isn't Saved", async () => {
    serve();
    const user = userEvent.setup();
    renderApp("/jobs/new");
    await screen.findByLabelText("Status");
    expect(screen.queryByLabelText("Applied on")).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Status"), "applied");
    expect(screen.getByLabelText("Applied on")).toHaveAccessibleDescription(
      "Leave blank for today",
    );
  });
});

describe("the draft", () => {
  it("brings back what you typed after a sign-in round trip", async () => {
    serve();
    const user = userEvent.setup();
    const first = renderApp(EXTENSION_URL);
    await user.type(await screen.findByLabelText("Company *"), "Acme");
    await user.type(screen.getByLabelText("Location"), "London");
    first.unmount();

    // Back from signing in: the same pre-filled URL.
    renderApp(EXTENSION_URL);
    expect(await screen.findByLabelText("Company *")).toHaveValue("Acme");
    expect(screen.getByLabelText("Location")).toHaveValue("London");
  });

  it("says so when a save was cut short by an expired session, without resubmitting", async () => {
    const { requests } = serve({
      "POST /api/jobs": () => json({ detail: "Not authenticated" }, 401),
    });
    const assign = vi.spyOn(navigation, "assign").mockImplementation(() => {});
    const user = userEvent.setup();
    const first = renderApp(EXTENSION_URL);
    await user.type(await screen.findByLabelText("Company *"), "Acme");
    await user.click(screen.getByRole("button", { name: "Save job" }));
    await waitFor(() => expect(assign).toHaveBeenCalled()); // off to sign in
    await waitFor(() =>
      expect(window.sessionStorage.getItem(INTERRUPTED_KEY)).not.toBeNull(),
    );
    first.unmount();
    navigation.leaving = false;

    // Back from signing in, on the same pre-filled URL.
    renderApp(EXTENSION_URL);
    expect(
      await screen.findByText(/You were signed out before this was saved/),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Company *")).toHaveValue("Acme");
    expect(requests.filter((r) => r.method === "POST")).toHaveLength(1); // not resubmitted
  });

  it("survives the sign-in round trip re-encoding the link (| comes back as %7C)", async () => {
    serve({
      "POST /api/jobs": () => json({ detail: "Not authenticated" }, 401),
    });
    vi.spyOn(navigation, "assign").mockImplementation(() => {});
    const user = userEvent.setup();
    const typed =
      "/jobs/new?url=https%3A%2F%2Fwww.linkedin.com%2Fjobs%2Fview%2F42&title=SRE%20|%20LinkedIn";
    const first = renderApp(typed);
    await user.type(await screen.findByLabelText("Company *"), "Acme");
    await user.type(screen.getByLabelText("Location"), "London");
    await user.click(screen.getByRole("button", { name: "Save job" }));
    await waitFor(() =>
      expect(window.sessionStorage.getItem(INTERRUPTED_KEY)).not.toBeNull(),
    );
    first.unmount();
    navigation.leaving = false;

    renderApp(typed.replaceAll("|", "%7C"));
    expect(
      await screen.findByText(/You were signed out before this was saved/),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Company *")).toHaveValue("Acme");
    expect(screen.getByLabelText("Location")).toHaveValue("London");
  });

  it("marks the save before sending (so a fast unload can't lose it), and clears it after", async () => {
    let finish!: () => void;
    serve({
      "POST /api/jobs": () =>
        new Promise((resolve) => {
          finish = () =>
            resolve(
              json(
                { detail: [{ loc: ["body", "role"], msg: "Too long" }] },
                422,
              ),
            );
        }),
    });
    const user = userEvent.setup();
    renderApp(EXTENSION_URL);
    await user.type(await screen.findByLabelText("Company *"), "Acme");
    await user.click(screen.getByRole("button", { name: "Save job" }));
    // In flight: already marked, before any answer.
    await waitFor(() =>
      expect(window.sessionStorage.getItem(INTERRUPTED_KEY)).not.toBeNull(),
    );
    finish();
    // An answer other than a 401: no longer interrupted.
    await waitFor(() =>
      expect(window.sessionStorage.getItem(INTERRUPTED_KEY)).toBeNull(),
    );
  });

  it("doesn't show that notice on a different job's form", async () => {
    window.sessionStorage.setItem(
      INTERRUPTED_KEY,
      "?url=https%3A%2F%2Fother.test%2F1",
    );
    serve();
    renderApp(EXTENSION_URL);
    await screen.findByLabelText("Company *");
    expect(screen.queryByText(/You were signed out/)).not.toBeInTheDocument();
  });

  it("doesn't carry over to a different job", async () => {
    serve();
    const user = userEvent.setup();
    const first = renderApp(EXTENSION_URL);
    await user.type(await screen.findByLabelText("Company *"), "Acme");
    first.unmount();

    renderApp(
      "/jobs/new?url=https%3A%2F%2Fjobs.lever.co%2Fglobex%2F1&title=SRE",
    );
    expect(await screen.findByLabelText("Company *")).toHaveValue("");
    expect(screen.getByLabelText("Role *")).toHaveValue("SRE");
  });

  it("is dropped on Cancel, which goes back to the jobs list", async () => {
    serve();
    const user = userEvent.setup();
    const { router } = renderApp(EXTENSION_URL);
    await user.type(await screen.findByLabelText("Company *"), "Acme");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/jobs"));
    expect(window.sessionStorage.getItem(DRAFT_KEY)).toBeNull();
  });
});

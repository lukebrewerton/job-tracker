// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Interview } from "../../api/interviews";
import type { Job } from "../../api/jobs";
import { json, mockApi, renderApp } from "../../test/utils";

const ME = { email: "luke@example.test", timezone: "Europe/London" };
const ID = "0199aaaa-0000-7000-8000-000000000001";

function job(overrides: Partial<Job> = {}): Job {
  return {
    id: ID,
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
    created_at: "2026-09-01T09:00:00Z",
    updated_at: "2026-09-10T09:00:00Z",
    last_status_change_at: "2026-09-10T09:00:00Z",
    days_since_last_change: 2,
    attention: null,
    ...overrides,
  };
}

function interview(overrides: Partial<Interview> = {}): Interview {
  return {
    id: crypto.randomUUID(),
    job_id: ID,
    scheduled_at: null,
    mode: null,
    round_label: null,
    notes: null,
    created_at: "2026-09-10T09:00:00Z",
    ...overrides,
  };
}

type Handlers = Parameters<typeof mockApi>[0];

/** Serve a job and its interviews; POST/PATCH/DELETE update the list, like the API. */
function serve(
  initial: Interview[] = [],
  jobOverrides: Partial<Job> = {},
  extra: Handlers = {},
) {
  let list = [...initial];
  const sent: { method: string; body: unknown }[] = [];
  const api = mockApi({
    "GET /api/v1/me": () => json(ME),
    [`GET /api/v1/jobs/${ID}`]: () => json(job(jobOverrides)),
    [`GET /api/v1/jobs/${ID}/history`]: () => json([]),
    [`GET /api/v1/jobs/${ID}/interviews`]: () => json(list),
    [`POST /api/v1/jobs/${ID}/interviews`]: async (request) => {
      const body: unknown = await request.json();
      sent.push({ method: "POST", body });
      const created: Interview = Object.assign(interview(), body);
      list = [...list, created];
      return json(created, 201);
    },
    ...Object.fromEntries(
      initial.flatMap((i) => [
        [
          `PATCH /api/v1/jobs/${ID}/interviews/${i.id}`,
          async (request: Request) => {
            const body: unknown = await request.json();
            sent.push({ method: "PATCH", body });
            list = list.map((x) =>
              x.id === i.id ? Object.assign({ ...x }, body) : x,
            );
            return json(list.find((x) => x.id === i.id));
          },
        ],
        [
          `DELETE /api/v1/jobs/${ID}/interviews/${i.id}`,
          () => {
            sent.push({ method: "DELETE", body: null });
            list = list.filter((x) => x.id !== i.id);
            return new Response(null, { status: 204 });
          },
        ],
      ]),
    ),
    ...extra,
  });
  return { ...api, sent };
}

const section = async () => screen.findByRole("region", { name: "Interviews" });

beforeEach(() => {
  const real = new Intl.DateTimeFormat().resolvedOptions();
  vi.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions").mockReturnValue({
    ...real,
    timeZone: ME.timezone,
  });
});
afterEach(() => vi.unstubAllGlobals());

describe("listing", () => {
  it("shows each interview's round, date and time or 'Not yet scheduled', and mode", async () => {
    serve([
      interview({
        round_label: "Technical",
        scheduled_at: "2030-10-02T13:00:00Z",
        mode: "remote",
        notes: "Bring a laptop",
      }),
      interview({ round_label: null }),
    ]);
    renderApp(`/jobs/${ID}`);
    const list = await within(await section()).findByRole("list");
    const [technical, unscheduled] = within(list).getAllByRole("listitem");
    expect(technical).toHaveTextContent("Technical");
    expect(technical).toHaveTextContent("Wed 2 Oct 2030, 14:00 · Remote"); // 13:00 UTC = 14:00 BST
    expect(technical).toHaveTextContent("Bring a laptop");
    expect(unscheduled).toHaveTextContent("Interview");
    expect(unscheduled).toHaveTextContent("Not yet scheduled");
  });

  it("marks past interviews", async () => {
    serve([
      interview({ round_label: "Final", scheduled_at: "2020-01-01T10:00:00Z" }),
    ]);
    renderApp(`/jobs/${ID}`);
    expect(
      await within(await section()).findByText("(past)"),
    ).toBeInTheDocument();
  });

  it("scrolls into view when linked to as #interviews", async () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView; // jsdom lacks it
    serve([interview({ round_label: "Technical" })]);
    renderApp(`/jobs/${ID}#interviews`);
    const region = await section();
    await within(region).findByText("Technical");
    expect(scrollIntoView.mock.contexts).toContain(region);
  });

  it("says when there are none", async () => {
    serve();
    renderApp(`/jobs/${ID}`);
    expect(
      await within(await section()).findByText("No interviews yet."),
    ).toBeInTheDocument();
  });
});

describe("adding", () => {
  it("creates an interview without a date", async () => {
    const { sent } = serve();
    const user = userEvent.setup();
    renderApp(`/jobs/${ID}`);
    await user.click(
      within(await section()).getByRole("button", { name: "Add interview" }),
    );
    const form = screen.getByRole("form", { name: "Add interview" });
    await user.selectOptions(
      within(form).getByLabelText("Round"),
      "Phone screen",
    );
    await user.click(
      within(form).getByRole("button", { name: "Add interview" }),
    );

    await waitFor(() =>
      expect(sent).toContainEqual({
        method: "POST",
        body: {
          round_label: "Phone screen",
          scheduled_at: null,
          mode: null,
          notes: null,
        },
      }),
    );
    expect(
      await within(await section()).findByText("Phone screen"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("form", { name: "Add interview" }),
    ).not.toBeInTheDocument();
  });

  it("sends the date and time with the offset in force on that day", async () => {
    const { sent } = serve();
    const user = userEvent.setup();
    renderApp(`/jobs/${ID}`);
    await user.click(
      within(await section()).getByRole("button", { name: "Add interview" }),
    );
    const form = screen.getByRole("form", { name: "Add interview" });
    await user.type(
      within(form).getByLabelText("Date and time"),
      "2030-10-02T14:00",
    );
    await user.selectOptions(within(form).getByLabelText("Mode"), "in_person");
    await user.click(
      within(form).getByRole("button", { name: "Add interview" }),
    );
    await waitFor(() =>
      expect(sent[0]?.body).toMatchObject({
        scheduled_at: "2030-10-02T14:00:00+01:00",
        mode: "in_person",
      }),
    );
  });

  it("round-trips a custom round via Other…", async () => {
    const { sent } = serve();
    const user = userEvent.setup();
    renderApp(`/jobs/${ID}`);
    await user.click(
      within(await section()).getByRole("button", { name: "Add interview" }),
    );
    let form = screen.getByRole("form", { name: "Add interview" });
    expect(within(form).queryByLabelText("Round name")).not.toBeInTheDocument();
    await user.selectOptions(within(form).getByLabelText("Round"), "__other__");
    await user.type(
      within(form).getByLabelText("Round name"),
      "Pairing session",
    );
    await user.click(
      within(form).getByRole("button", { name: "Add interview" }),
    );
    await waitFor(() =>
      expect(sent[0]?.body).toMatchObject({ round_label: "Pairing session" }),
    );

    // Editing it opens on Other… with the text filled in.
    await user.click(
      await within(await section()).findByRole("button", {
        name: /Edit the Pairing session/,
      }),
    );
    form = screen.getByRole("form", { name: "Edit interview" });
    expect(within(form).getByLabelText("Round")).toHaveValue("__other__");
    expect(within(form).getByLabelText("Round name")).toHaveValue(
      "Pairing session",
    );
  });

  it("then offers to move a saved or applied job to Interviewing", async () => {
    let statusSent: unknown;
    serve(
      [],
      { status: "applied" },
      {
        [`POST /api/v1/jobs/${ID}/status`]: async (request) => {
          statusSent = await request.json();
          return json(job({ status: "interviewing" }));
        },
      },
    );
    const user = userEvent.setup();
    renderApp(`/jobs/${ID}`);
    await user.click(
      within(await section()).getByRole("button", { name: "Add interview" }),
    );
    await user.click(
      within(screen.getByRole("form", { name: "Add interview" })).getByRole(
        "button",
        {
          name: "Add interview",
        },
      ),
    );
    const prompt = await screen.findByText("Move this job to Interviewing?");
    await user.click(
      within(prompt.parentElement!).getByRole("button", { name: "Yes" }),
    );
    await waitFor(() => expect(statusSent).toEqual({ status: "interviewing" }));
    expect(
      screen.queryByText("Move this job to Interviewing?"),
    ).not.toBeInTheDocument();
  });

  it("doesn't offer that when the job is already further along", async () => {
    serve([], { status: "offer" });
    const user = userEvent.setup();
    renderApp(`/jobs/${ID}`);
    await user.click(
      within(await section()).getByRole("button", { name: "Add interview" }),
    );
    await user.click(
      within(screen.getByRole("form", { name: "Add interview" })).getByRole(
        "button",
        {
          name: "Add interview",
        },
      ),
    );
    await within(await section()).findByText("Interview");
    expect(
      screen.queryByText("Move this job to Interviewing?"),
    ).not.toBeInTheDocument();
  });
});

describe("editing and deleting", () => {
  it("edits inline, sending the changes", async () => {
    const existing = interview({ round_label: "Technical" });
    const { sent } = serve([existing]);
    const user = userEvent.setup();
    renderApp(`/jobs/${ID}`);
    await user.click(
      await within(await section()).findByRole("button", {
        name: /Edit the Technical/,
      }),
    );
    const form = screen.getByRole("form", { name: "Edit interview" });
    await user.selectOptions(within(form).getByLabelText("Mode"), "phone");
    await user.click(
      within(form).getByRole("button", { name: "Save interview" }),
    );
    await waitFor(() =>
      expect(sent).toContainEqual({
        method: "PATCH",
        body: {
          round_label: "Technical",
          scheduled_at: null,
          mode: "phone",
          notes: null,
        },
      }),
    );
    expect(
      await within(await section()).findByText(/Phone/),
    ).toBeInTheDocument();
  });

  it("deletes only after confirming", async () => {
    const existing = interview({ round_label: "Panel" });
    const { sent } = serve([existing]);
    const user = userEvent.setup();
    renderApp(`/jobs/${ID}`);
    await user.click(
      await within(await section()).findByRole("button", {
        name: /Delete the Panel/,
      }),
    );
    const dialog = screen.getByRole("dialog", {
      name: "Delete this interview?",
    });
    expect(dialog).toHaveTextContent(
      "Delete the Panel (not yet scheduled)? This can't be undone.",
    );

    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(sent).toEqual([]);

    await user.click(
      within(await section()).getByRole("button", { name: /Delete the Panel/ }),
    );
    await user.click(
      within(
        screen.getByRole("dialog", { name: "Delete this interview?" }),
      ).getByRole("button", {
        name: "Delete interview",
      }),
    );
    await waitFor(() =>
      expect(sent).toContainEqual({ method: "DELETE", body: null }),
    );
    expect(
      await within(await section()).findByText("No interviews yet."),
    ).toBeInTheDocument();
  });
});

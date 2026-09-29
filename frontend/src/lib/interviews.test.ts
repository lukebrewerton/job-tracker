// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";

import { formatWhenRelative, fromLocalInput, toLocalInput } from "./interviews";

// Vitest runs with TZ=Europe/London (see vitest.config.ts): BST in summer, GMT in winter.
describe("datetime-local conversion", () => {
  it("adds the offset in force on that date", () => {
    expect(fromLocalInput("2026-10-02T14:00")).toBe(
      "2026-10-02T14:00:00+01:00",
    ); // BST
    expect(fromLocalInput("2026-11-02T14:00")).toBe(
      "2026-11-02T14:00:00+00:00",
    ); // GMT
  });

  it("round-trips through the picker's format", () => {
    expect(toLocalInput("2026-10-02T13:00:00Z")).toBe("2026-10-02T14:00");
    expect(toLocalInput(fromLocalInput("2026-12-24T09:30"))).toBe(
      "2026-12-24T09:30",
    );
  });
});

describe("formatWhenRelative", () => {
  const now = new Date("2026-10-01T22:30:00Z"); // 23:30 on Thu 1 Oct in London

  it("says Today or Tomorrow by the local calendar", () => {
    expect(formatWhenRelative("2026-10-01T22:45:00Z", now)).toBe(
      "Today, 23:45",
    );
    // 23:30 UTC is already 00:30 on Fri 2 Oct in London.
    expect(formatWhenRelative("2026-10-01T23:30:00Z", now)).toBe(
      "Tomorrow, 00:30",
    );
  });

  it("gives the full date otherwise", () => {
    expect(formatWhenRelative("2026-10-03T13:00:00Z", now)).toBe(
      "Sat 3 Oct 2026, 14:00",
    );
    expect(formatWhenRelative("2026-09-30T13:00:00Z", now)).toBe(
      "Wed 30 Sept 2026, 14:00",
    );
  });
});

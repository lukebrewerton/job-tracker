// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";

import { fromLocalInput, toLocalInput } from "./interviews";

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

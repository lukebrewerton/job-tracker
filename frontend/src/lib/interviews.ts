// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import type { InterviewMode } from "../api/interviews";

/** Offered as options; anything else is entered via "Other…" and stored as text. */
export const ROUND_PRESETS = [
  "Phone screen",
  "Recruiter call",
  "Technical",
  "Take-home",
  "Hiring manager",
  "Panel",
  "Final",
] as const;

export const MODE_LABELS: Record<InterviewMode, string> = {
  remote: "Remote",
  in_person: "In person",
  phone: "Phone",
};

export const MODES: readonly InterviewMode[] = ["remote", "in_person", "phone"];

const pad = (n: number) => String(n).padStart(2, "0");

/** An instant as a <input type="datetime-local"> value, in the browser's zone. */
export function toLocalInput(isoInstant: string): string {
  const d = new Date(isoInstant);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/**
 * A datetime-local value ("2026-10-02T14:00", local time) as an ISO string with the
 * browser's offset at that moment ("2026-10-02T14:00:00+01:00"): the API needs to know
 * when it actually is. The offset is the one in force on that date, so BST/GMT is right.
 */
export function fromLocalInput(value: string): string {
  const d = new Date(value); // parsed as local time
  const offset = -d.getTimezoneOffset();
  const sign = offset >= 0 ? "+" : "-";
  const hours = pad(Math.floor(Math.abs(offset) / 60));
  const minutes = pad(Math.abs(offset) % 60);
  return `${value.length === 16 ? `${value}:00` : value}${sign}${hours}:${minutes}`;
}

function part(d: Date, options: Intl.DateTimeFormatOptions): string {
  return new Intl.DateTimeFormat("en-GB", options).format(d);
}

/** "Thu 2 Oct", in the browser's zone (no comma after the weekday). */
export function formatDay(isoInstant: string): string {
  const d = new Date(isoInstant);
  return `${part(d, { weekday: "short" })} ${part(d, { day: "numeric", month: "short" })}`;
}

/** "Thu 2 Oct 2026, 14:00", in the browser's zone. */
export function formatWhen(isoInstant: string): string {
  const d = new Date(isoInstant);
  const year = part(d, { year: "numeric" });
  const time = part(d, { hour: "2-digit", minute: "2-digit" });
  return `${formatDay(isoInstant)} ${year}, ${time}`;
}

const sameDay = (a: Date, b: Date) =>
  a.getFullYear() === b.getFullYear() &&
  a.getMonth() === b.getMonth() &&
  a.getDate() === b.getDate();

/** "Today, 14:00", "Tomorrow, 14:00", else as formatWhen: in the browser's zone. */
export function formatWhenRelative(
  isoInstant: string,
  now: Date = new Date(),
): string {
  const d = new Date(isoInstant);
  const tomorrow = new Date(now);
  tomorrow.setDate(now.getDate() + 1);
  const time = part(d, { hour: "2-digit", minute: "2-digit" });
  if (sameDay(d, now)) return `Today, ${time}`;
  if (sameDay(d, tomorrow)) return `Tomorrow, ${time}`;
  return formatWhen(isoInstant);
}

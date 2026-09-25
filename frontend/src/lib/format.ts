// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import type { components } from "../api/schema";

export type JobStatus = components["schemas"]["JobStatus"];
export type Attention = NonNullable<
  components["schemas"]["JobOut"]["attention"]
>;

export const STATUS_LABELS: Record<JobStatus, string> = {
  saved: "Saved",
  applied: "Applied",
  interviewing: "Interviewing",
  offer: "Offer",
  accepted: "Accepted",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
  no_response: "No response",
};

/** In lifecycle order, as the API sorts them. */
export const STATUSES: readonly JobStatus[] = [
  "saved",
  "applied",
  "interviewing",
  "offer",
  "accepted",
  "rejected",
  "withdrawn",
  "no_response",
];

export const ACTIVE_STATUSES: readonly JobStatus[] = [
  "saved",
  "applied",
  "interviewing",
  "offer",
];

export const ATTENTION_LABELS: Record<Attention, string> = {
  needs_follow_up: "Follow up",
  still_to_apply: "Still to apply",
  no_response: "No response?",
};

/** A calendar date ("2026-09-25") as "25 Sep 2026", without any time-zone shift. */
export function formatDate(isoDate: string | null | undefined): string {
  if (!isoDate) return "—";
  const [year, month, day] = isoDate.split("-").map(Number);
  if (!year || !month || !day) return isoDate;
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(Date.UTC(year, month - 1, day));
}

/** An instant as a date in the browser's own zone, e.g. "25 Sep 2026". */
export function formatInstantDate(isoInstant: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(isoInstant));
}

export function daysLabel(days: number): string {
  if (days <= 0) return "Today";
  if (days === 1) return "1 day";
  return `${days} days`;
}

// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import type { Attention, JobStatus } from "./format";

/** At least 44px tall: a comfortable touch target. */
export const tapTarget = "inline-flex min-h-11 items-center rounded-md px-3";

export const inputClass =
  "mt-1 min-h-11 w-full rounded-md border border-slate-300 bg-white px-3";
export const labelClass = "block text-sm font-medium text-slate-700";

export const STATUS_BADGE: Record<JobStatus, string> = {
  saved: "bg-slate-100 text-slate-700",
  applied: "bg-blue-100 text-blue-800",
  interviewing: "bg-violet-100 text-violet-800",
  offer: "bg-emerald-100 text-emerald-800",
  accepted: "bg-emerald-200 text-emerald-900",
  rejected: "bg-rose-100 text-rose-800",
  withdrawn: "bg-slate-200 text-slate-700",
  no_response: "bg-amber-100 text-amber-800",
};

// Needs attention: a tint plus a text label, so meaning never rests on colour alone.
export const ATTENTION_STYLE: Record<
  Attention,
  { row: string; label: string }
> = {
  needs_follow_up: { row: "bg-amber-50", label: "bg-amber-200 text-amber-900" },
  still_to_apply: { row: "bg-sky-50", label: "bg-sky-200 text-sky-900" },
  no_response: { row: "bg-rose-50", label: "bg-rose-200 text-rose-900" },
};

// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later

export const NAV_LINKS = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/jobs", label: "Jobs" },
  { to: "/interviews", label: "Interviews" },
] as const;

// Where "Sign in" goes: the dashboard, not back to the public front page.
export const SIGN_IN_URL = `/auth/login?next=${encodeURIComponent("/dashboard")}`;

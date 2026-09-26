// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later

export const NAV_LINKS = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/jobs", label: "Jobs" },
  { to: "/interviews", label: "Interviews" },
] as const;

// Signing in on purpose: Google's account chooser (in case its current account isn't the
// one for this app), then the dashboard rather than back to the public front page.
// Automatic redirects (an expired session, the extension's link) stay silent and fast.
export const SIGN_IN_URL = `/auth/login?switch_account=true&next=${encodeURIComponent("/dashboard")}`;

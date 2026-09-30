// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { api, unwrap } from "./client";
import type { components } from "./schema";

export type Dashboard = components["schemas"]["DashboardOut"];
export type DashboardCounts = components["schemas"]["DashboardCounts"];
export type StaleJob = components["schemas"]["StaleJobOut"];

export function getDashboard(): Promise<Dashboard> {
  return unwrap(api.GET("/api/v1/dashboard"));
}

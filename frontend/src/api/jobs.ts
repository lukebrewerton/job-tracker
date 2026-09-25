// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { api, unwrap } from "./client";
import type { components, paths } from "./schema";

export type Job = components["schemas"]["JobOut"];
export type JobPage = components["schemas"]["JobPage"];
export type JobListQuery = NonNullable<
  paths["/api/jobs"]["get"]["parameters"]["query"]
>;

export function listJobs(query: JobListQuery): Promise<JobPage> {
  return unwrap(api.GET("/api/jobs", { params: { query } }));
}

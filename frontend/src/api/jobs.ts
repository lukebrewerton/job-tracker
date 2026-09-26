// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { api, ApiError, unwrap } from "./client";
import type { components, paths } from "./schema";

export type Job = components["schemas"]["JobOut"];
export type JobPage = components["schemas"]["JobPage"];
export type JobListQuery = NonNullable<
  paths["/api/jobs"]["get"]["parameters"]["query"]
>;

export function listJobs(query: JobListQuery): Promise<JobPage> {
  return unwrap(api.GET("/api/jobs", { params: { query } }));
}

export type JobCreate = components["schemas"]["JobCreate"];
export type CompanyMatch = components["schemas"]["CompanyMatch"];

/** Created, or already tracked (409): the existing job's id. Other failures throw. */
export type CreateResult = { created: Job } | { existingId: string };

export async function createJob(body: JobCreate): Promise<CreateResult> {
  const { data, error, response } = await api.POST("/api/jobs", { body });
  if (response.status === 409 && error && "existing_id" in error) {
    return { existingId: error.existing_id };
  }
  if (!response.ok || !data) throw new ApiError(response.status, error);
  return { created: data };
}

export async function companyMatches(company: string): Promise<CompanyMatch[]> {
  const result = await unwrap(
    api.GET("/api/jobs/company-matches", { params: { query: { company } } }),
  );
  return result.companies;
}

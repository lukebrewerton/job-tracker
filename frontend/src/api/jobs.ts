// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { api, ApiError, expectNoContent, unwrap } from "./client";
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

export type JobUpdate = components["schemas"]["JobUpdate"];
export type HistoryEntry = components["schemas"]["HistoryEntry"];
export type JobStatusValue = components["schemas"]["JobStatus"];

export function getJob(id: string): Promise<Job> {
  return unwrap(
    api.GET("/api/jobs/{job_id}", { params: { path: { job_id: id } } }),
  );
}

/** Saved, or the new URL is another job's (409): its id. Other failures throw. */
export type UpdateResult = { updated: Job } | { existingId: string };

export async function updateJob(
  id: string,
  changes: JobUpdate,
): Promise<UpdateResult> {
  const { data, error, response } = await api.PATCH("/api/jobs/{job_id}", {
    params: { path: { job_id: id } },
    body: changes,
  });
  if (response.status === 409 && error && "existing_id" in error) {
    return { existingId: error.existing_id };
  }
  if (!response.ok || !data) throw new ApiError(response.status, error);
  return { updated: data };
}

export function changeStatus(id: string, status: JobStatusValue): Promise<Job> {
  return unwrap(
    api.POST("/api/jobs/{job_id}/status", {
      params: { path: { job_id: id } },
      body: { status },
    }),
  );
}

export function jobHistory(id: string): Promise<HistoryEntry[]> {
  return unwrap(
    api.GET("/api/jobs/{job_id}/history", { params: { path: { job_id: id } } }),
  );
}

export async function deleteJob(id: string): Promise<void> {
  await expectNoContent(
    api.DELETE("/api/jobs/{job_id}", { params: { path: { job_id: id } } }),
  );
}

export async function interviewCount(jobId: string): Promise<number> {
  const interviews = await unwrap(
    api.GET("/api/jobs/{job_id}/interviews", {
      params: { path: { job_id: jobId } },
    }),
  );
  return interviews.length;
}

// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { api, expectNoContent, unwrap } from "./client";
import type { components } from "./schema";

export type Interview = components["schemas"]["InterviewOut"];
export type InterviewInput = components["schemas"]["InterviewCreate"];
export type InterviewMode = components["schemas"]["InterviewMode"];
export type InterviewWithJob = components["schemas"]["InterviewWithJob"];
export type InterviewGroups = components["schemas"]["InterviewGroups"];

/** All your interviews: upcoming, not yet scheduled and past. */
export function listInterviewGroups(): Promise<InterviewGroups> {
  return unwrap(api.GET("/api/v1/interviews"));
}

export function listInterviews(jobId: string): Promise<Interview[]> {
  return unwrap(
    api.GET("/api/v1/jobs/{job_id}/interviews", {
      params: { path: { job_id: jobId } },
    }),
  );
}

export function createInterview(
  jobId: string,
  body: InterviewInput,
): Promise<Interview> {
  return unwrap(
    api.POST("/api/v1/jobs/{job_id}/interviews", {
      params: { path: { job_id: jobId } },
      body,
    }),
  );
}

export function updateInterview(
  jobId: string,
  interviewId: string,
  body: InterviewInput,
): Promise<Interview> {
  return unwrap(
    api.PATCH("/api/v1/jobs/{job_id}/interviews/{interview_id}", {
      params: { path: { job_id: jobId, interview_id: interviewId } },
      body,
    }),
  );
}

export async function deleteInterview(
  jobId: string,
  interviewId: string,
): Promise<void> {
  await expectNoContent(
    api.DELETE("/api/v1/jobs/{job_id}/interviews/{interview_id}", {
      params: { path: { job_id: jobId, interview_id: interviewId } },
    }),
  );
}

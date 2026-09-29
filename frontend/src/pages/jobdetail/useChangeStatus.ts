// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { ApiError } from "../../api/client";
import { changeStatus, type Job } from "../../api/jobs";
import type { ErrorMeta } from "../../api/queryClient";
import type { JobStatus } from "../../lib/format";

export const jobKey = (id: string) => ["job", id] as const;
export const historyKey = (id: string) => ["job-history", id] as const;
export const interviewsKey = (jobId: string) =>
  ["job-interviews", jobId] as const;

/**
 * Change a job's status: shown straight away (optimistic), put back visibly with a toast
 * if the save fails, and the history, jobs list and dashboard refreshed afterwards.
 */
export function useChangeStatus(jobId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (status: JobStatus) => changeStatus(jobId, status),
    meta: { silent: true } satisfies ErrorMeta, // its own toast below
    onMutate: async (status) => {
      await queryClient.cancelQueries({ queryKey: jobKey(jobId) });
      const previous = queryClient.getQueryData<Job>(jobKey(jobId));
      if (previous)
        queryClient.setQueryData<Job>(jobKey(jobId), { ...previous, status });
      return { previous };
    },
    onError: (error, _status, context) => {
      if (context?.previous)
        queryClient.setQueryData(jobKey(jobId), context.previous);
      if (error instanceof ApiError && error.status === 401) return; // off to sign in
      toast.error(`Couldn't change the status: ${error.message}`);
    },
    onSuccess: (updated) => queryClient.setQueryData(jobKey(jobId), updated),
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: historyKey(jobId) }),
        queryClient.invalidateQueries({ queryKey: ["jobs"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      ]),
  });
}

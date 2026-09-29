// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// The dashboard: counts by status, the jobs that need attention (one rule, shared with
// the jobs table's highlighting: app/dashboard.py) and the next interviews.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useRef, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";

import { ApiError } from "../../api/client";
import {
  type Dashboard,
  type DashboardCounts,
  getDashboard,
  type StaleJob,
} from "../../api/dashboard";
import type { InterviewWithJob } from "../../api/interviews";
import { bulkChangeStatus, changeStatus } from "../../api/jobs";
import type { ErrorMeta } from "../../api/queryClient";
import { daysLabel } from "../../lib/format";
import { formatWhenRelative, MODE_LABELS } from "../../lib/interviews";
import { tapTarget } from "../../lib/styles";

const DASHBOARD = ["dashboard"] as const;
const MARK_ONE = ["mark-no-response"] as const;
/** Rows shown per list before "Show all". */
const LIST_PREVIEW = 5;

const plural = (n: number, one: string, many = `${one}s`) =>
  `${n} ${n === 1 ? one : many}`;

// --- Tiles -----------------------------------------------------------------------------

function Tile({
  label,
  count,
  to,
  detail,
}: {
  label: string;
  count: number;
  to?: string;
  detail?: string;
}) {
  const body = (
    <>
      <div className="text-2xl font-semibold">{count}</div>
      <div className="text-sm text-slate-600">{label}</div>
      {detail && <div className="mt-1 text-xs text-slate-500">{detail}</div>}
    </>
  );
  const box = "block h-full rounded-lg border border-slate-200 bg-white p-3";
  return (
    <li>
      {to ? (
        <Link to={to} className={`${box} hover:border-slate-400`}>
          {body}
        </Link>
      ) : (
        <div className={box}>{body}</div>
      )}
    </li>
  );
}

function Tiles({ counts }: { counts: DashboardCounts }) {
  const byStatus = (status: string) => `/jobs?status=${status}`;
  const rejected =
    counts.rejected_at_application + counts.rejected_after_interview;
  return (
    <ul
      aria-label="Counts"
      className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5"
    >
      <Tile label="Active" count={counts.active} to={byStatus("active")} />
      <Tile label="Saved" count={counts.saved} to={byStatus("saved")} />
      {/* Every job with an applied date, whatever its status now: no filter matches. */}
      <Tile label="Applied" count={counts.applied_ever} />
      <Tile
        label="Interviewing"
        count={counts.interviewing}
        to={byStatus("interviewing")}
      />
      <Tile label="Offer" count={counts.offer} to={byStatus("offer")} />
      <Tile
        label="Accepted"
        count={counts.accepted}
        to={byStatus("accepted")}
      />
      <Tile
        label="Rejected"
        count={rejected}
        to={byStatus("rejected")}
        detail={`${counts.rejected_at_application} at application · ${counts.rejected_after_interview} after interview`}
      />
      <Tile
        label="No response"
        count={counts.no_response}
        to={byStatus("no_response")}
      />
      <Tile
        label="Withdrawn"
        count={counts.withdrawn}
        to={byStatus("withdrawn")}
      />
    </ul>
  );
}

// --- Needs-attention lists -------------------------------------------------------------

function JobList({
  id,
  title,
  description,
  jobs,
  empty,
  onMark,
  headerAction,
}: {
  id: string;
  title: string;
  description: string;
  jobs: StaleJob[];
  empty: string;
  /** Adds a per-row "Mark as no response" button. */
  onMark?: (job: StaleJob) => void;
  headerAction?: ReactNode;
}) {
  const [showAll, setShowAll] = useState(false);
  const shown = showAll ? jobs : jobs.slice(0, LIST_PREVIEW);
  return (
    <section aria-labelledby={id}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 id={id} className="text-lg font-semibold">
            {title} ({jobs.length})
          </h2>
          <p className="text-sm text-slate-600">{description}</p>
        </div>
        {jobs.length > 0 && headerAction}
      </div>
      {jobs.length === 0 ? (
        <p className="mt-2 text-slate-600">{empty}</p>
      ) : (
        <ul className="mt-2 divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
          {shown.map((job) => (
            <li
              key={job.id}
              className="flex flex-col gap-2 p-3 sm:flex-row sm:items-center sm:justify-between"
            >
              <Link to={`/jobs/${job.id}`} className="min-w-0 hover:underline">
                <span className="font-medium">{job.company}</span>
                <span className="text-slate-600"> · {job.role}</span>
                <span className="block text-sm text-slate-500">
                  {daysLabel(job.days_since_last_change)} without movement
                </span>
              </Link>
              {onMark && (
                <button
                  type="button"
                  onClick={() => onMark(job)}
                  aria-label={`Mark ${job.company}, ${job.role} as no response`}
                  className={`${tapTarget} shrink-0 self-start border border-slate-300 bg-white text-sm sm:self-auto`}
                >
                  Mark as no response
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {jobs.length > LIST_PREVIEW && (
        <button
          type="button"
          onClick={() => setShowAll(!showAll)}
          className={`${tapTarget} mt-1 -ml-3 text-sm text-slate-700 hover:underline`}
        >
          {showAll ? "Show fewer" : `Show all (${jobs.length})`}
        </button>
      )}
    </section>
  );
}

/** Mark one job as no response: its row goes at once; the counts follow on refetch. */
function useMarkNoResponse() {
  const queryClient = useQueryClient();
  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: DASHBOARD }),
      queryClient.invalidateQueries({ queryKey: ["jobs"] }),
    ]);
  return useMutation({
    mutationKey: MARK_ONE,
    mutationFn: (job: StaleJob) => changeStatus(job.id, "no_response"),
    meta: { silent: true } satisfies ErrorMeta, // its own toast below
    onMutate: async (job) => {
      await queryClient.cancelQueries({ queryKey: DASHBOARD });
      queryClient.setQueryData<Dashboard>(DASHBOARD, (old) =>
        old
          ? {
              ...old,
              no_response_candidates: old.no_response_candidates.filter(
                (j) => j.id !== job.id,
              ),
            }
          : old,
      );
    },
    onSuccess: (_updated, job) =>
      toast.success(`Marked ${job.company} as no response`),
    onError: (error, job) => {
      if (error instanceof ApiError && error.status === 401) return; // off to sign in
      toast.error(`Couldn't mark ${job.company}: ${error.message}`);
    },
    // Refetch once the last of several quick marks is done: an earlier refetch would
    // briefly bring back rows still being marked.
    onSettled: () =>
      queryClient.isMutating({ mutationKey: MARK_ONE }) === 1
        ? refresh()
        : undefined,
  });
}

function NoResponseList({ jobs, days }: { jobs: StaleJob[]; days: number }) {
  const queryClient = useQueryClient();
  const markOne = useMarkNoResponse();
  const dialog = useRef<HTMLDialogElement>(null);
  // The jobs on screen when "Mark all" was pressed: only those are marked.
  const [confirming, setConfirming] = useState<StaleJob[]>([]);

  const markAll = useMutation({
    mutationFn: (toMark: StaleJob[]) =>
      bulkChangeStatus(
        toMark.map((j) => j.id),
        "no_response",
      ),
    onSuccess: async (result) => {
      dialog.current?.close();
      toast.success(
        `Marked ${plural(result.updated.length, "job")} as no response`,
      );
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: DASHBOARD }),
        queryClient.invalidateQueries({ queryKey: ["jobs"] }),
      ]);
    },
  });

  return (
    <>
      <JobList
        id="no-response-heading"
        title="No response?"
        description={`Applied, with no movement for ${days}+ days.`}
        jobs={jobs}
        empty="Nothing waiting that long."
        onMark={(job) => markOne.mutate(job)}
        headerAction={
          <button
            type="button"
            onClick={() => {
              setConfirming(jobs);
              dialog.current?.showModal();
            }}
            className={`${tapTarget} border border-slate-300 bg-white text-sm`}
          >
            Mark all as no response
          </button>
        }
      />
      <dialog
        ref={dialog}
        aria-labelledby="mark-all-heading"
        className="m-auto max-w-md rounded-lg p-6 backdrop:bg-slate-900/50"
      >
        <h2 id="mark-all-heading" className="text-lg font-semibold">
          Mark all as no response?
        </h2>
        <p className="mt-2 text-slate-700">
          Mark {plural(confirming.length, "job")} as no response? You can change
          any of them back from its page.
        </p>
        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={() => dialog.current?.close()}
            className={`${tapTarget} border border-slate-300`}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => markAll.mutate(confirming)}
            disabled={markAll.isPending}
            className={`${tapTarget} bg-slate-900 font-medium text-white disabled:opacity-50`}
          >
            {markAll.isPending
              ? "Marking…"
              : `Mark ${plural(confirming.length, "job")}`}
          </button>
        </div>
      </dialog>
    </>
  );
}

// --- Upcoming interviews ---------------------------------------------------------------

function UpcomingInterviews({
  interviews,
  total,
}: {
  interviews: InterviewWithJob[];
  total: number;
}) {
  return (
    <section aria-labelledby="upcoming-heading">
      <h2 id="upcoming-heading" className="text-lg font-semibold">
        Upcoming interviews
      </h2>
      {interviews.length === 0 ? (
        <p className="mt-2 text-slate-600">No upcoming interviews.</p>
      ) : (
        <ul className="mt-2 divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
          {interviews.map((interview) => (
            <li key={interview.id}>
              <Link
                to={`/jobs/${interview.job.id}#interviews`}
                className="block p-3 hover:bg-slate-50"
              >
                <span className="block text-sm font-medium">
                  {interview.scheduled_at &&
                    formatWhenRelative(interview.scheduled_at)}
                </span>
                <span className="block">
                  {interview.round_label ?? "Interview"}
                  {interview.mode && ` · ${MODE_LABELS[interview.mode]}`}
                </span>
                <span className="block text-sm text-slate-600">
                  {interview.job.company} · {interview.job.role}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <Link
        to="/interviews"
        className={`${tapTarget} mt-1 -ml-3 text-sm text-slate-700 hover:underline`}
      >
        {total > 0 ? `View all (${total})` : "Go to interviews"}
      </Link>
    </section>
  );
}

// --- Page ------------------------------------------------------------------------------

function hasNoJobs(counts: DashboardCounts): boolean {
  const closed =
    counts.accepted +
    counts.rejected_at_application +
    counts.rejected_after_interview +
    counts.withdrawn +
    counts.no_response;
  return counts.active + closed === 0;
}

export function DashboardPage() {
  const { data, isPending, isError } = useQuery({
    queryKey: DASHBOARD,
    queryFn: getDashboard,
  });

  const content = () => {
    if (isPending) {
      return (
        <div aria-busy="true" aria-label="Loading the dashboard">
          <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
            {Array.from({ length: 9 }, (_, i) => (
              <div
                key={i}
                className="h-20 animate-pulse rounded-lg bg-slate-200"
              />
            ))}
          </div>
        </div>
      );
    }
    if (isError) {
      return (
        <p className="mt-6 text-slate-600">Couldn&apos;t load the dashboard.</p>
      );
    }
    if (hasNoJobs(data.counts)) {
      return (
        <div className="mt-6 rounded-lg border border-dashed border-slate-300 p-8 text-center">
          <p className="text-slate-600">No jobs yet.</p>
          <Link
            to="/jobs/new"
            className={`${tapTarget} mt-4 bg-slate-900 font-medium text-white`}
          >
            Add a job
          </Link>
        </div>
      );
    }
    const { stale_after_days: stale, no_response_after_days: noResponse } =
      data.thresholds;
    return (
      <>
        <Tiles counts={data.counts} />
        {/* Interviews come first in the source: after the tiles on mobile, a side
            column from lg up. */}
        <div className="mt-8 grid gap-8 lg:grid-cols-3">
          <div className="lg:col-start-3 lg:row-start-1">
            <UpcomingInterviews
              interviews={data.upcoming_interviews}
              total={data.upcoming_interviews_total}
            />
          </div>
          <div className="space-y-8 lg:col-span-2 lg:row-start-1">
            <NoResponseList
              jobs={data.no_response_candidates}
              days={noResponse}
            />
            <JobList
              id="follow-up-heading"
              title="Needs follow-up"
              description={`Applied or offered, with no movement for ${stale}+ days: time to chase.`}
              jobs={data.needs_follow_up}
              empty="Nothing to chase."
            />
            <JobList
              id="still-to-apply-heading"
              title="Still to apply"
              description={`Saved ${stale}+ days ago and not applied for yet.`}
              jobs={data.still_to_apply}
              empty="Nothing waiting."
            />
          </div>
        </div>
      </>
    );
  };

  return (
    <section>
      <h1 className="text-2xl font-semibold">Dashboard</h1>
      {content()}
    </section>
  );
}

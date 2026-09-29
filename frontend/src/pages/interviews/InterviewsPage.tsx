// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Every interview across your jobs, in three groups. Read-only: interviews are added
// and edited on their job's page, which each row links to.
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";

import {
  type InterviewWithJob,
  listInterviewGroups,
} from "../../api/interviews";
import { StatusBadge } from "../../components/Badges";
import { formatWhenRelative, MODE_LABELS } from "../../lib/interviews";
import { tapTarget } from "../../lib/styles";

const jobLink = (interview: InterviewWithJob) =>
  `/jobs/${interview.job.id}#interviews`;

const round = (interview: InterviewWithJob) =>
  interview.round_label ?? "Interview";

const mode = (interview: InterviewWithJob) =>
  interview.mode ? MODE_LABELS[interview.mode] : "—";

const when = (interview: InterviewWithJob) =>
  interview.scheduled_at
    ? formatWhenRelative(interview.scheduled_at)
    : "Not yet scheduled";

function InterviewList({
  interviews,
  showWhen = true,
  past = false,
}: {
  interviews: InterviewWithJob[];
  showWhen?: boolean;
  past?: boolean;
}) {
  const navigate = useNavigate();
  const tone = past ? "text-slate-500" : "";
  return (
    <>
      {/* Table from md up. */}
      <div className="hidden overflow-x-auto rounded-lg border border-slate-200 bg-white md:block">
        <table className={`w-full text-left text-sm ${tone}`}>
          <thead className="border-b border-slate-200 bg-slate-50 text-slate-600">
            <tr>
              {showWhen && (
                <th scope="col" className="px-3 py-2 font-medium">
                  When
                </th>
              )}
              <th scope="col" className="px-3 py-2 font-medium">
                Round
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Mode
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Job
              </th>
            </tr>
          </thead>
          <tbody>
            {interviews.map((interview) => (
              <tr
                key={interview.id}
                onClick={() => void navigate(jobLink(interview))}
                className="cursor-pointer border-b border-slate-100 last:border-0 hover:bg-slate-100"
              >
                {showWhen && (
                  <td className="px-3 py-2 whitespace-nowrap">
                    {when(interview)}
                  </td>
                )}
                <td className="px-3 py-2">{round(interview)}</td>
                <td className="px-3 py-2">{mode(interview)}</td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    {/* A real link, so the row works by keyboard and as a link. */}
                    <Link
                      to={jobLink(interview)}
                      className="font-medium hover:underline"
                    >
                      {interview.job.company}
                    </Link>
                    <span className="text-slate-600">{interview.job.role}</span>
                    <StatusBadge status={interview.job.status} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Cards below md. */}
      <ul className={`space-y-2 md:hidden ${tone}`}>
        {interviews.map((interview) => (
          <li key={interview.id}>
            <Link
              to={jobLink(interview)}
              className="block min-h-11 rounded-lg border border-slate-200 bg-white p-3"
            >
              <div className="font-medium">
                {round(interview)}
                {interview.mode && (
                  <span className="font-normal"> · {mode(interview)}</span>
                )}
              </div>
              {showWhen && <div className="text-sm">{when(interview)}</div>}
              <div className="mt-2 text-sm">
                {interview.job.company}
                <span className="text-slate-600"> · {interview.job.role}</span>
              </div>
              <div className="mt-1">
                <StatusBadge status={interview.job.status} />
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}

function Group({
  id,
  title,
  interviews,
  showWhen,
}: {
  id: string;
  title: string;
  interviews: InterviewWithJob[];
  showWhen?: boolean;
}) {
  return (
    <section aria-labelledby={id} className="mt-6">
      <h2 id={id} className="mb-2 text-lg font-semibold">
        {title} ({interviews.length})
      </h2>
      {interviews.length === 0 ? (
        <p className="text-slate-600">None.</p>
      ) : (
        <InterviewList interviews={interviews} showWhen={showWhen} />
      )}
    </section>
  );
}

export function InterviewsPage() {
  const { data, isPending, isError } = useQuery({
    queryKey: ["interviews"],
    queryFn: listInterviewGroups,
  });

  const content = () => {
    if (isPending) {
      return (
        <div
          aria-busy="true"
          aria-label="Loading interviews"
          className="mt-6 space-y-2"
        >
          {Array.from({ length: 4 }, (_, i) => (
            <div
              key={i}
              className="h-12 animate-pulse rounded-md bg-slate-200"
            />
          ))}
        </div>
      );
    }
    if (isError) {
      return (
        <p className="mt-6 text-slate-600">
          Couldn&apos;t load your interviews.
        </p>
      );
    }
    const { upcoming, not_yet_scheduled: unscheduled, past } = data;
    if (upcoming.length + unscheduled.length + past.length === 0) {
      return (
        <div className="mt-6 rounded-lg border border-dashed border-slate-300 p-8 text-center">
          <p className="text-slate-600">
            No interviews yet. Add them from a job&apos;s page.
          </p>
          <Link
            to="/jobs"
            className={`${tapTarget} mt-4 border border-slate-300 bg-white`}
          >
            Go to jobs
          </Link>
        </div>
      );
    }
    return (
      <>
        <Group id="upcoming-heading" title="Upcoming" interviews={upcoming} />
        <Group
          id="unscheduled-heading"
          title="Not yet scheduled"
          interviews={unscheduled}
          showWhen={false}
        />
        {past.length > 0 && (
          <section aria-label="Past" className="mt-6">
            <details>
              <summary className="min-h-11 cursor-pointer py-2 text-lg font-semibold">
                Past ({past.length})
              </summary>
              <InterviewList interviews={past} past />
            </details>
          </section>
        )}
      </>
    );
  };

  return (
    <section>
      <h1 className="text-2xl font-semibold">Interviews</h1>
      {content()}
    </section>
  );
}

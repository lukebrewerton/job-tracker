// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  createColumnHelper,
  tableFeatures,
  useTable,
} from "@tanstack/react-table";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router";

import { type Job, listJobs } from "../../api/jobs";
import { AttentionLabel, StatusBadge } from "../../components/Badges";
import {
  ACTIVE_STATUSES,
  daysLabel,
  formatDate,
  formatInstantDate,
  STATUS_LABELS,
  STATUSES,
} from "../../lib/format";
import { ATTENTION_STYLE, tapTarget } from "../../lib/styles";
import {
  DEFAULT_VIEW,
  PAGE_SIZES,
  isPageSize,
  type SortField,
  type StatusFilter,
  useJobsView,
} from "./useJobsView";

const MIN_SEARCH_CHARS = 2;
const SEARCH_DELAY_MS = 300;

const target = tapTarget;

const features = tableFeatures({});
const column = createColumnHelper<typeof features, Job>();

const COLUMNS: { id: SortField; label: string }[] = [
  { id: "company", label: "Company" },
  { id: "role", label: "Role" },
  { id: "status", label: "Status" },
  { id: "last_status_change", label: "Last movement" },
  { id: "applied_at", label: "Applied" },
  { id: "created_at", label: "Added" },
];

const columns = column.columns([
  column.accessor("company", {
    id: "company",
    cell: (info) => <span className="font-medium">{info.getValue()}</span>,
  }),
  column.accessor("role", { id: "role" }),
  column.accessor("status", {
    id: "status",
    cell: (info) => (
      <span className="flex flex-wrap gap-1">
        <StatusBadge status={info.getValue()} />
        <AttentionLabel attention={info.row.original.attention} />
      </span>
    ),
  }),
  column.accessor("days_since_last_change", {
    id: "last_status_change",
    cell: (info) => daysLabel(info.getValue()),
  }),
  column.accessor("applied_at", {
    id: "applied_at",
    cell: (info) => formatDate(info.getValue()),
  }),
  column.accessor("created_at", {
    id: "created_at",
    cell: (info) => formatInstantDate(info.getValue()),
  }),
]);

function SearchBox({
  initial,
  onSearch,
}: {
  initial: string;
  onSearch: (q: string) => void;
}) {
  const [text, setText] = useState(initial);
  // Follow the URL's search when it changes from outside (Reset, the back button),
  // without overwriting what's being typed (e.g. "acme " mid-word).
  const [seen, setSeen] = useState(initial);
  if (initial !== seen) {
    setSeen(initial);
    if (initial !== text.trim()) setText(initial);
  }
  const trimmed = text.trim();
  const tooShort = trimmed.length > 0 && trimmed.length < MIN_SEARCH_CHARS;

  useEffect(() => {
    if (tooShort || trimmed === initial) return () => {};
    const timer = setTimeout(() => onSearch(trimmed), SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [trimmed, tooShort, initial, onSearch]);

  return (
    <div className="w-full sm:max-w-xs">
      <label htmlFor="jobs-search" className="sr-only">
        Search company or role
      </label>
      <input
        id="jobs-search"
        type="search"
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder="Search company or role"
        aria-describedby={tooShort ? "jobs-search-hint" : undefined}
        className="min-h-11 w-full rounded-md border border-slate-300 bg-white px-3"
      />
      {tooShort && (
        <p id="jobs-search-hint" className="mt-1 text-sm text-slate-600">
          Enter at least {MIN_SEARCH_CHARS} characters
        </p>
      )}
    </div>
  );
}

export function JobsPage() {
  const { view, update, reset } = useJobsView();
  const navigate = useNavigate();

  const query = useQuery({
    queryKey: ["jobs", view],
    queryFn: () =>
      listJobs({
        status: view.status,
        q: view.q || undefined,
        sort: view.sort,
        order: view.order,
        page: view.page,
        page_size: view.size,
      }),
    placeholderData: keepPreviousData, // keep the rows on screen while the next ones load
  });
  const page = query.data;
  const jobs = page?.items ?? [];

  const table = useTable({ features, columns, data: jobs });

  const counts = page?.counts;
  const filterCount = (filter: StatusFilter): number | undefined => {
    if (!counts) return undefined;
    if (filter === "all")
      return Object.values(counts).reduce((a, b) => a + b, 0);
    if (filter === "active")
      return ACTIVE_STATUSES.reduce((sum, s) => sum + (counts[s] ?? 0), 0);
    return counts[filter];
  };
  const filters: { id: StatusFilter; label: string }[] = [
    { id: "active", label: "Active" },
    { id: "all", label: "All" },
    ...STATUSES.map((s) => ({ id: s, label: STATUS_LABELS[s] })),
  ];

  const sortBy = (field: SortField) =>
    update(
      view.sort === field
        ? { order: view.order === "asc" ? "desc" : "asc" }
        : {
            sort: field,
            order: field === "company" || field === "role" ? "asc" : "desc",
          },
    );

  const isDefault =
    view.status === DEFAULT_VIEW.status &&
    !view.q &&
    view.sort === DEFAULT_VIEW.sort &&
    view.order === DEFAULT_VIEW.order &&
    view.size === DEFAULT_VIEW.size;
  const hasNoJobs = counts !== undefined && filterCount("all") === 0;
  const first =
    page && page.total > 0 ? (page.page - 1) * page.page_size + 1 : 0;
  const last = page ? Math.min(page.page * page.page_size, page.total) : 0;
  const lastPage = page
    ? Math.max(1, Math.ceil(page.total / page.page_size))
    : 1;

  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Jobs</h1>
        <div className="flex w-full flex-wrap items-start gap-2 sm:w-auto">
          <SearchBox initial={view.q} onSearch={(q) => update({ q })} />
          {!isDefault && (
            <button
              type="button"
              onClick={reset}
              className={`${target} border border-slate-300 bg-white`}
            >
              Reset
            </button>
          )}
        </div>
      </div>

      {/* Below md, one dropdown: a row of ten buttons doesn't fit a phone. */}
      <div className="mt-4 md:hidden">
        <label htmlFor="jobs-status" className="text-sm text-slate-600">
          Status
        </label>
        <select
          id="jobs-status"
          value={view.status}
          onChange={(event) => {
            const chosen = filters.find((f) => f.id === event.target.value);
            if (chosen) update({ status: chosen.id });
          }}
          className="mt-1 min-h-11 w-full rounded-md border border-slate-300 bg-white px-3"
        >
          {filters.map(({ id, label }) => {
            const count = filterCount(id);
            return (
              <option key={id} value={id}>
                {count === undefined ? label : `${label} (${count})`}
              </option>
            );
          })}
        </select>
      </div>

      {/* From md up, buttons that wrap rather than scroll. */}
      <fieldset className="mt-4 hidden flex-wrap gap-2 md:flex">
        <legend className="sr-only">Filter by status</legend>
        {filters.map(({ id, label }) => {
          const selected = view.status === id;
          const count = filterCount(id);
          return (
            <button
              key={id}
              type="button"
              aria-pressed={selected}
              onClick={() => update({ status: id })}
              className={`${target} gap-2 border ${
                selected
                  ? "border-slate-900 bg-slate-900 text-white"
                  : "border-slate-300 bg-white text-slate-700"
              }`}
            >
              {label}
              {count !== undefined && (
                <span
                  className={`text-xs ${selected ? "text-slate-200" : "text-slate-500"}`}
                >
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </fieldset>

      <div className="mt-4">
        {query.isPending ? (
          <div aria-busy="true" aria-label="Loading jobs" className="space-y-2">
            {Array.from({ length: 5 }, (_, i) => (
              <div
                key={i}
                className="h-12 animate-pulse rounded-md bg-slate-200"
              />
            ))}
          </div>
        ) : hasNoJobs ? (
          <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center">
            <p className="text-slate-600">No jobs yet.</p>
            <Link
              to="/jobs/new"
              className={`${target} mt-4 bg-slate-900 font-medium text-white`}
            >
              Add a job
            </Link>
          </div>
        ) : jobs.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center">
            <p className="text-slate-600">No jobs match.</p>
            <button
              type="button"
              onClick={reset}
              className={`${target} mt-4 border border-slate-300 bg-white`}
            >
              Reset
            </button>
          </div>
        ) : (
          <>
            {/* Table from md up. */}
            <div className="hidden overflow-x-auto rounded-lg border border-slate-200 bg-white md:block">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-slate-200 bg-slate-50">
                  <tr>
                    {COLUMNS.map(({ id, label }) => {
                      const sorted = view.sort === id;
                      return (
                        <th
                          key={id}
                          scope="col"
                          aria-sort={
                            sorted
                              ? view.order === "asc"
                                ? "ascending"
                                : "descending"
                              : "none"
                          }
                          className="px-2 py-1 font-medium text-slate-600"
                        >
                          <button
                            type="button"
                            onClick={() => sortBy(id)}
                            className={`${target} -mx-1 gap-1 px-1 hover:text-slate-900`}
                          >
                            {label}
                            <span
                              aria-hidden="true"
                              className={sorted ? "" : "invisible"}
                            >
                              {view.order === "asc" ? "↑" : "↓"}
                            </span>
                          </button>
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody>
                  {table.getRowModel().rows.map((row) => {
                    const job = row.original;
                    return (
                      <tr
                        key={row.id}
                        onClick={() => void navigate(`/jobs/${job.id}`)}
                        className={`cursor-pointer border-b border-slate-100 last:border-0 hover:bg-slate-100 ${
                          job.attention
                            ? ATTENTION_STYLE[job.attention].row
                            : ""
                        }`}
                      >
                        {row.getAllCells().map((cell, i) => (
                          <td key={cell.id} className="px-3 py-2 align-middle">
                            {i === 0 ? (
                              // A real link, so the row works by keyboard and as a link.
                              <Link
                                to={`/jobs/${job.id}`}
                                className="hover:underline"
                              >
                                <table.FlexRender cell={cell} />
                              </Link>
                            ) : (
                              <table.FlexRender cell={cell} />
                            )}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Cards below md. */}
            <ul className="space-y-2 md:hidden">
              {jobs.map((job) => (
                <li key={job.id}>
                  <Link
                    to={`/jobs/${job.id}`}
                    className={`block min-h-11 rounded-lg border border-slate-200 p-3 ${
                      job.attention
                        ? ATTENTION_STYLE[job.attention].row
                        : "bg-white"
                    }`}
                  >
                    <div className="font-medium">{job.company}</div>
                    <div className="text-sm text-slate-600">{job.role}</div>
                    <div className="mt-2 flex flex-wrap items-center gap-1">
                      <StatusBadge status={job.status} />
                      <AttentionLabel attention={job.attention} />
                    </div>
                    <div className="mt-2 flex gap-4 text-sm text-slate-600">
                      <span>
                        Last movement: {daysLabel(job.days_since_last_change)}
                      </span>
                      {job.applied_at && (
                        <span>Applied: {formatDate(job.applied_at)}</span>
                      )}
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      {page && page.total > 0 && (
        <nav
          aria-label="Pages"
          className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm"
        >
          <p className="text-slate-600">
            Showing {first}–{last} of {page.total}
          </p>
          <div className="flex items-center gap-2">
            <label htmlFor="jobs-page-size" className="text-slate-600">
              Per page
            </label>
            <select
              id="jobs-page-size"
              value={view.size}
              onChange={(event) => {
                const size = Number(event.target.value);
                if (isPageSize(size)) update({ size });
              }}
              className="min-h-11 rounded-md border border-slate-300 bg-white px-2"
            >
              {PAGE_SIZES.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
            <button
              type="button"
              disabled={view.page <= 1}
              onClick={() => update({ page: view.page - 1 })}
              className={`${target} border border-slate-300 bg-white disabled:opacity-40`}
            >
              Previous
            </button>
            <button
              type="button"
              disabled={view.page >= lastPage}
              onClick={() => update({ page: view.page + 1 })}
              className={`${target} border border-slate-300 bg-white disabled:opacity-40`}
            >
              Next
            </button>
          </div>
        </nav>
      )}
    </section>
  );
}

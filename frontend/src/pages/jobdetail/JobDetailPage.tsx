// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// /jobs/:id: the job's details, edited in place; its status (saved immediately, with
// an optimistic update); its status history; and deleting it.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { Link, useBlocker, useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import { ApiError } from "../../api/client";
import {
  changeStatus,
  deleteJob,
  getJob,
  interviewCount,
  type Job,
  jobHistory,
  type JobUpdate,
  updateJob,
} from "../../api/jobs";
import type { ErrorMeta } from "../../api/queryClient";
import { AttentionLabel, StatusBadge } from "../../components/Badges";
import { Field } from "../../components/Field";
import {
  daysAgo,
  daysLabel,
  formatDateTime,
  type JobStatus,
  STATUS_LABELS,
  STATUSES,
} from "../../lib/format";
import { validationMessages } from "../../lib/formErrors";
import { SOURCE_LABELS, SOURCES } from "../../lib/source";
import { inputClass, tapTarget } from "../../lib/styles";

type FieldName =
  | "company"
  | "role"
  | "url"
  | "location"
  | "source"
  | "applied_at"
  | "salary"
  | "contact_name"
  | "contact_email"
  | "notes";
type Fields = Record<FieldName, string>;

const FIELD_NAMES: ReadonlySet<FieldName> = new Set<FieldName>([
  "company",
  "role",
  "url",
  "location",
  "source",
  "applied_at",
  "salary",
  "contact_name",
  "contact_email",
  "notes",
]);

function fromJob(job: Job): Fields {
  return {
    company: job.company,
    role: job.role,
    url: job.url ?? "",
    location: job.location ?? "",
    source: job.source ?? "",
    applied_at: job.applied_at ?? "",
    salary: job.salary ?? "",
    contact_name: job.contact_name ?? "",
    contact_email: job.contact_email ?? "",
    notes: job.notes ?? "",
  };
}

const FIELD_LIST: readonly FieldName[] = [...FIELD_NAMES];
const OPTIONAL_TEXT = [
  "url",
  "location",
  "applied_at",
  "salary",
  "contact_name",
  "contact_email",
  "notes",
] as const;

/** Only the fields that changed, as the API wants them (blank optional fields = null). */
function changesBody(changed: Partial<Fields>): JobUpdate {
  const body: JobUpdate = {};
  if (changed.company !== undefined) body.company = changed.company.trim();
  if (changed.role !== undefined) body.role = changed.role.trim();
  if (changed.source !== undefined) {
    body.source = SOURCES.find((s) => s === changed.source) ?? null;
  }
  for (const name of OPTIONAL_TEXT) {
    const value = changed[name];
    if (value !== undefined) body[name] = value.trim() || null;
  }
  return body;
}

const jobKey = (id: string) => ["job", id] as const;
const historyKey = (id: string) => ["job-history", id] as const;

function StatusPicker({ job }: { job: Job }) {
  const queryClient = useQueryClient();
  const change = useMutation({
    mutationFn: (status: JobStatus) => changeStatus(job.id, status),
    meta: { silent: true } satisfies ErrorMeta, // its own toast below
    // Optimistic: show the new status straight away...
    onMutate: async (status) => {
      await queryClient.cancelQueries({ queryKey: jobKey(job.id) });
      const previous = queryClient.getQueryData<Job>(jobKey(job.id));
      if (previous)
        queryClient.setQueryData<Job>(jobKey(job.id), { ...previous, status });
      return { previous };
    },
    // ...and put it back, visibly, if the save fails.
    onError: (error, _status, context) => {
      if (context?.previous)
        queryClient.setQueryData(jobKey(job.id), context.previous);
      if (error instanceof ApiError && error.status === 401) return; // off to sign in
      toast.error(`Couldn't change the status: ${error.message}`);
    },
    onSuccess: (updated) => queryClient.setQueryData(jobKey(job.id), updated),
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: historyKey(job.id) }),
        queryClient.invalidateQueries({ queryKey: ["jobs"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      ]),
  });

  return (
    <div>
      <label
        htmlFor="job-status"
        className="block text-sm font-medium text-slate-700"
      >
        Status
      </label>
      <select
        id="job-status"
        value={job.status}
        disabled={change.isPending}
        onChange={(event) => {
          const status = STATUSES.find((s) => s === event.target.value);
          if (status && status !== job.status) change.mutate(status);
        }}
        className={`${inputClass} md:w-60`}
      >
        {STATUSES.map((status) => (
          <option key={status} value={status}>
            {STATUS_LABELS[status]}
          </option>
        ))}
      </select>
    </div>
  );
}

function Timeline({ jobId }: { jobId: string }) {
  const { data: history, isPending } = useQuery({
    queryKey: historyKey(jobId),
    queryFn: () => jobHistory(jobId),
  });
  return (
    <section aria-labelledby="history-heading">
      <h2 id="history-heading" className="text-lg font-semibold">
        Status history
      </h2>
      {isPending ? (
        <div className="mt-3 h-24 animate-pulse rounded-md bg-slate-200" />
      ) : (
        <ol className="mt-3 space-y-3 border-l-2 border-slate-200 pl-4">
          {history?.map((entry, i) => (
            <li key={`${entry.changed_at}-${i}`}>
              <StatusBadge status={entry.status} />
              <p className="mt-1 text-sm text-slate-600">
                {formatDateTime(entry.changed_at)} ({daysAgo(entry.changed_at)})
              </p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function DeleteJob({ job, onDeleted }: { job: Job; onDeleted: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [open, setOpen] = useState(false);
  const { data: interviews } = useQuery({
    queryKey: ["job-interview-count", job.id],
    queryFn: () => interviewCount(job.id),
    enabled: open,
  });
  const remove = useMutation({
    mutationFn: () => deleteJob(job.id),
    onSuccess: onDeleted,
  });

  const show = () => {
    setOpen(true);
    dialog.current?.showModal();
  };
  const hide = () => dialog.current?.close();

  const alsoDeleted =
    interviews === undefined
      ? "Its status history and interviews will be deleted too."
      : interviews === 0
        ? "Its status history will be deleted too."
        : `Its status history and ${interviews} interview${interviews === 1 ? "" : "s"} will be deleted too.`;

  return (
    <>
      <button
        type="button"
        onClick={show}
        className={`${tapTarget} border border-rose-300 bg-white text-rose-700 hover:bg-rose-50`}
      >
        Delete job
      </button>
      <dialog
        ref={dialog}
        aria-labelledby="delete-heading"
        onClose={() => setOpen(false)}
        className="m-auto max-w-md rounded-lg p-6 backdrop:bg-slate-900/50"
      >
        <h2 id="delete-heading" className="text-lg font-semibold">
          Delete this job?
        </h2>
        <p className="mt-2 text-slate-700">
          Delete{" "}
          <strong>
            {job.company}, {job.role}
          </strong>
          ? {alsoDeleted} This can't be undone.
        </p>
        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={hide}
            className={`${tapTarget} border border-slate-300`}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => remove.mutate()}
            disabled={remove.isPending}
            className={`${tapTarget} bg-rose-700 font-medium text-white disabled:opacity-50`}
          >
            {remove.isPending ? "Deleting…" : "Delete job"}
          </button>
        </div>
      </dialog>
    </>
  );
}

function Details({ job }: { job: Job }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const base = fromJob(job);
  const [edits, setEdits] = useState<Partial<Fields>>({});
  const [errors, setErrors] = useState<
    Partial<Record<FieldName | "form", string>>
  >({});
  const [existingId, setExistingId] = useState<string | null>(null);
  const leavingOnPurpose = useRef(false);

  const value = (name: FieldName) => edits[name] ?? base[name];
  const changed: Partial<Fields> = {};
  for (const name of FIELD_LIST) {
    const edited = edits[name];
    if (edited !== undefined && edited !== base[name]) changed[name] = edited;
  }
  const dirty = Object.keys(changed).length > 0;

  // Leaving with unsaved changes: ask first (in the app, and when closing the tab).
  const blocker = useBlocker(({ currentLocation, nextLocation }) => {
    return (
      dirty &&
      !leavingOnPurpose.current &&
      currentLocation.pathname !== nextLocation.pathname
    );
  });
  useEffect(() => {
    if (blocker.state !== "blocked") return;
    if (window.confirm("Discard your changes?")) blocker.proceed();
    else blocker.reset();
  }, [blocker]);
  useEffect(() => {
    if (!dirty) return () => {};
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const save = useMutation({
    mutationFn: () => updateJob(job.id, changesBody(changed)),
    meta: { inlineValidation: true } satisfies ErrorMeta,
    onSuccess: async (result) => {
      if ("existingId" in result) {
        setExistingId(result.existingId);
        return;
      }
      queryClient.setQueryData(jobKey(job.id), result.updated);
      setEdits({});
      toast.success("Changes saved");
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 422) {
        setErrors(validationMessages(error, FIELD_NAMES));
      }
    },
  });

  const set = (name: FieldName) => (next: string) =>
    setEdits((current) => ({ ...current, [name]: next }));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setErrors({});
    setExistingId(null);
    save.mutate();
  };

  const discard = () => {
    setEdits({});
    setErrors({});
    setExistingId(null);
  };

  const onDeleted = () => {
    leavingOnPurpose.current = true;
    queryClient.removeQueries({ queryKey: jobKey(job.id) });
    void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    toast.success("Job deleted");
    void navigate("/jobs", { replace: true });
  };

  const text = (name: FieldName, label: string, required = false) => (
    <Field
      id={`job-${name}`}
      text={required ? `${label} *` : label}
      error={errors[name]}
    >
      {(props) => (
        <input
          {...props}
          required={required}
          value={value(name)}
          onChange={(e) => set(name)(e.target.value)}
          className={inputClass}
        />
      )}
    </Field>
  );

  return (
    <>
      <form onSubmit={submit} className="space-y-4" aria-label="Job details">
        {existingId && (
          <div
            role="alert"
            className="rounded-md bg-amber-50 px-4 py-3 text-amber-900"
          >
            <p className="font-medium">Another job already has this URL</p>
            <Link to={`/jobs/${existingId}`} className="font-medium underline">
              View that job
            </Link>
          </div>
        )}
        {errors.form && (
          <p
            role="alert"
            className="rounded-md bg-rose-50 px-4 py-3 text-rose-800"
          >
            {errors.form}
          </p>
        )}
        <div className="grid gap-4 md:grid-cols-2">
          {text("company", "Company", true)}
          {text("role", "Role", true)}
        </div>
        {text("url", "Job URL")}
        <div className="grid gap-4 md:grid-cols-2">
          <Field id="job-source" text="Source" error={errors.source}>
            {(props) => (
              <select
                {...props}
                value={value("source")}
                onChange={(e) => set("source")(e.target.value)}
                className={inputClass}
              >
                <option value="">Not set</option>
                {SOURCES.map((source) => (
                  <option key={source} value={source}>
                    {SOURCE_LABELS[source]}
                  </option>
                ))}
              </select>
            )}
          </Field>
          {text("location", "Location")}
          {job.status !== "saved" && (
            <Field
              id="job-applied_at"
              text="Applied on"
              error={errors.applied_at}
            >
              {(props) => (
                <input
                  {...props}
                  type="date"
                  value={value("applied_at")}
                  onChange={(e) => set("applied_at")(e.target.value)}
                  className={inputClass}
                />
              )}
            </Field>
          )}
          {text("salary", "Salary")}
          {text("contact_name", "Contact name")}
          {text("contact_email", "Contact email")}
        </div>
        <Field id="job-notes" text="Notes" error={errors.notes}>
          {(props) => (
            <textarea
              {...props}
              rows={5}
              value={value("notes")}
              onChange={(e) => set("notes")(e.target.value)}
              className={`${inputClass} py-2`}
            />
          )}
        </Field>

        {dirty && (
          // Phone: the message, then both buttons sharing the width below it.
          // From md up: one row, message left and buttons right.
          <div className="sticky bottom-0 -mx-4 flex flex-col gap-2 border-t border-slate-200 bg-white px-4 py-3 md:mx-0 md:flex-row md:items-center md:rounded-md md:border">
            <span className="text-sm text-slate-600 md:mr-auto">
              You have unsaved changes
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={discard}
                className={`${tapTarget} flex-1 justify-center border border-slate-300 bg-white md:flex-none`}
              >
                Discard
              </button>
              <button
                type="submit"
                disabled={save.isPending}
                className={`${tapTarget} flex-1 justify-center bg-slate-900 font-medium text-white disabled:opacity-50 md:flex-none`}
              >
                {save.isPending ? "Saving…" : "Save changes"}
              </button>
            </div>
          </div>
        )}
      </form>

      <div className="mt-8 border-t border-slate-200 pt-6">
        <DeleteJob job={job} onDeleted={onDeleted} />
      </div>
    </>
  );
}

export function JobDetailPage() {
  const { id = "" } = useParams();
  const {
    data: job,
    error,
    isPending,
  } = useQuery({
    queryKey: jobKey(id),
    queryFn: () => getJob(id),
    meta: { expectedStatuses: [404, 422] } satisfies ErrorMeta, // 422: not a valid id
  });

  if (isPending) {
    return (
      <div aria-busy="true" aria-label="Loading job" className="space-y-3">
        <div className="h-8 w-2/3 animate-pulse rounded bg-slate-200" />
        <div className="h-48 animate-pulse rounded bg-slate-200" />
      </div>
    );
  }

  if (!job) {
    const missing =
      error instanceof ApiError && [404, 422].includes(error.status);
    return (
      <section className="py-8 text-center">
        <h1 className="text-2xl font-semibold">
          {missing ? "Job not found" : "Couldn't load this job"}
        </h1>
        <Link
          to="/jobs"
          className={`${tapTarget} mt-6 bg-slate-900 font-medium text-white`}
        >
          Back to jobs
        </Link>
      </section>
    );
  }

  return (
    <article>
      <Link to="/jobs" className="text-sm text-slate-600 hover:underline">
        ← Jobs
      </Link>
      <header className="mt-2">
        <h1 className="text-2xl font-semibold">{job.company}</h1>
        <p className="text-lg text-slate-700">{job.role}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <StatusBadge status={job.status} />
          <AttentionLabel attention={job.attention} />
          <span>Last movement: {daysLabel(job.days_since_last_change)}</span>
          {job.url && (
            <a
              href={job.url}
              target="_blank"
              rel="noopener noreferrer"
              className="font-medium text-slate-900 underline"
            >
              View job posting ↗
            </a>
          )}
        </div>
      </header>

      <div className="mt-6">
        <StatusPicker job={job} />
      </div>

      <div className="mt-6 grid gap-8 md:grid-cols-[2fr_1fr]">
        <Details job={job} />
        <Timeline jobId={job.id} />
      </div>
    </article>
  );
}

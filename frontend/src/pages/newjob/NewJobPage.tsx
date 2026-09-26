// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// /jobs/new: the page the browser extension opens, pre-filled from ?url=&title=.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router";
import { toast } from "sonner";

import { ApiError } from "../../api/client";
import {
  type CompanyMatch,
  companyMatches,
  createJob,
  type JobCreate,
} from "../../api/jobs";
import type { ErrorMeta } from "../../api/queryClient";
import { Field } from "../../components/Field";
import { validationMessages } from "../../lib/formErrors";
import { inputClass } from "../../lib/styles";
import { type JobStatus, STATUS_LABELS, STATUSES } from "../../lib/format";
import { inferSource, SOURCE_LABELS, SOURCES } from "../../lib/source";
import { readItem, removeItem, writeItem } from "../../lib/storage";

export const DRAFT_KEY = "job-tracker.new-job-draft";
// Set when a save was cut short by an expired session, so the restored form can say so.
export const INTERRUPTED_KEY = "job-tracker.new-job-interrupted";
const COMPANY_CHECK_DELAY_MS = 400;
const MIN_COMPANY_CHARS = 2;

export interface Fields {
  company: string;
  role: string;
  url: string;
  status: JobStatus;
  source: string; // "" = not set
  location: string;
  applied_at: string;
  salary: string;
  contact_name: string;
  contact_email: string;
  notes: string;
}

type FieldName = keyof Fields;

const FIELD_NAMES: ReadonlySet<FieldName> = new Set<FieldName>([
  "company",
  "role",
  "url",
  "status",
  "source",
  "location",
  "applied_at",
  "salary",
  "contact_name",
  "contact_email",
  "notes",
]);

type FieldErrors = Partial<Record<FieldName | "form", string>>;

/**
 * Which pre-fill a draft belongs to: the decoded `url` and `title`, not the raw query
 * text, which differs by encoding alone (a sign-in round trip turns "|" into "%7C").
 */
function prefillKey(params: URLSearchParams): string {
  return JSON.stringify([params.get("url") ?? "", params.get("title") ?? ""]);
}

interface Draft {
  // The pre-fill the draft belongs to (see prefillKey): a new extension click starts afresh.
  search: string;
  fields: Fields;
}

function prefilled(params: URLSearchParams): Fields {
  const url = (params.get("url") ?? "").trim();
  return {
    company: "",
    role: (params.get("title") ?? "").trim(),
    url,
    status: "saved",
    source: inferSource(url) ?? "",
    location: "",
    applied_at: "",
    salary: "",
    contact_name: "",
    contact_email: "",
    notes: "",
  };
}

function isDraft(value: unknown): value is Draft {
  return (
    typeof value === "object" &&
    value !== null &&
    "search" in value &&
    typeof value.search === "string" &&
    "fields" in value &&
    typeof value.fields === "object" &&
    value.fields !== null
  );
}

/** The draft for this exact pre-fill, if one was saved (e.g. before a sign-in round trip). */
function restoreDraft(search: string): Fields | null {
  const raw = readItem(DRAFT_KEY, "session");
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    const params = new URLSearchParams(search);
    if (!isDraft(parsed) || parsed.search !== prefillKey(params)) return null;
    return { ...prefilled(params), ...parsed.fields };
  } catch {
    return null;
  }
}

function requestBody(fields: Fields): JobCreate {
  const optional = (value: string) => value.trim() || null;
  return {
    company: fields.company.trim(),
    role: fields.role.trim(),
    url: optional(fields.url),
    status: fields.status,
    source: SOURCES.find((s) => s === fields.source) ?? null,
    location: optional(fields.location),
    // A saved job can't have one; blank means "today" for the server to fill in.
    applied_at: fields.status === "saved" ? null : optional(fields.applied_at),
    salary: optional(fields.salary),
    contact_name: optional(fields.contact_name),
    contact_email: optional(fields.contact_email),
    notes: optional(fields.notes),
  };
}

function fieldErrors(error: ApiError): FieldErrors {
  return validationMessages(error, FIELD_NAMES);
}

function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

function statusSummary(match: CompanyMatch): string {
  const parts = STATUSES.flatMap((status) => {
    const count = match.by_status[status];
    return count ? [`${count} ${STATUS_LABELS[status].toLowerCase()}`] : [];
  });
  return `${match.total}: ${parts.join(", ")}`;
}

/** "You've tracked jobs at …": a soft warning, never blocking. */
function CompanyWarning({ company }: { company: string }) {
  const query = useDebounced(company.trim(), COMPANY_CHECK_DELAY_MS);
  const enabled = query.length >= MIN_COMPANY_CHARS;
  const { data: matches } = useQuery({
    queryKey: ["company-matches", query],
    queryFn: () => companyMatches(query),
    enabled,
    retry: false,
    // Mid-typing input like "a Ltd" is a 422: that just means "no warning".
    meta: { silent: true } satisfies ErrorMeta,
  });
  if (!enabled || !matches || matches.length === 0) return null;

  return (
    <output className="mt-2 block rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">
      You've tracked jobs at{" "}
      {matches.map((match, i) => (
        <span key={match.name}>
          {i > 0 && (i === matches.length - 1 ? " and " : ", ")}
          <Link
            to={`/jobs?${new URLSearchParams({ status: "all", q: match.name }).toString()}`}
            className="font-medium underline"
          >
            {match.name}
          </Link>{" "}
          ({statusSummary(match)})
        </span>
      ))}
      .
    </output>
  );
}

const input = inputClass;

export function NewJobPage() {
  const [params] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [fields, setFields] = useState<Fields>(
    () => restoreDraft(location.search) ?? prefilled(params),
  );
  const [errors, setErrors] = useState<FieldErrors>({});
  const [existingId, setExistingId] = useState<string | null>(null);
  // Back from signing in after a save that didn't happen: say so, don't resubmit.
  const [interrupted, setInterrupted] = useState(
    () => readItem(INTERRUPTED_KEY, "session") === prefillKey(params),
  );
  useEffect(() => removeItem(INTERRUPTED_KEY, "session"), []);

  // Keep a draft for this tab: survives the sign-in round trip if the session expired.
  useEffect(() => {
    const draft: Draft = { search: prefillKey(params), fields };
    writeItem(DRAFT_KEY, JSON.stringify(draft), "session");
  }, [fields, params]);

  const set = (name: FieldName) => (value: string) =>
    setFields((current) => ({ ...current, [name]: value }));

  const save = useMutation({
    mutationFn: async (body: JobCreate) => {
      // Marked before sending, cleared on any answer but a 401. If an expired session
      // sends the page off to sign in mid-save, the mark is simply still there on the
      // way back, however quickly the page unloads.
      writeItem(INTERRUPTED_KEY, prefillKey(params), "session");
      const result = await createJob(body);
      removeItem(INTERRUPTED_KEY, "session");
      return result;
    },
    meta: { inlineValidation: true } satisfies ErrorMeta,
    onSuccess: async (result) => {
      if ("existingId" in result) {
        setExistingId(result.existingId);
        return;
      }
      removeItem(DRAFT_KEY, "session");
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
      toast.success("Job added");
      void navigate(`/jobs/${result.created.id}`);
    },
    onError: (error) => {
      // Only a 401 (off to sign in) leaves the interrupted mark in place.
      if (!(error instanceof ApiError && error.status === 401)) {
        removeItem(INTERRUPTED_KEY, "session");
      }
      if (error instanceof ApiError && error.status === 422)
        setErrors(fieldErrors(error));
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setErrors({});
    setExistingId(null);
    setInterrupted(false);
    save.mutate(requestBody(fields));
  };

  const cancel = () => {
    removeItem(DRAFT_KEY, "session");
    void navigate("/jobs");
  };

  return (
    <section className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-semibold">New job</h1>

      {interrupted && (
        <output className="mt-4 block rounded-md bg-sky-50 px-4 py-3 text-sky-900">
          You were signed out before this was saved. Your details have been
          kept: press <strong>Save job</strong> to add it.
        </output>
      )}

      {existingId && (
        <div
          role="alert"
          className="mt-4 rounded-md bg-amber-50 px-4 py-3 text-amber-900"
        >
          <p className="font-medium">Already tracked</p>
          <p className="text-sm">You already have a job with this URL.</p>
          <Link
            to={`/jobs/${existingId}`}
            className="mt-1 inline-block font-medium underline"
          >
            View the existing job
          </Link>
        </div>
      )}
      {errors.form && (
        <p
          role="alert"
          className="mt-4 rounded-md bg-rose-50 px-4 py-3 text-rose-800"
        >
          {errors.form}
        </p>
      )}

      <form onSubmit={submit} className="mt-6 space-y-4">
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <Field id="new-job-company" text="Company *" error={errors.company}>
              {(props) => (
                <input
                  {...props}
                  required
                  value={fields.company}
                  onChange={(e) => set("company")(e.target.value)}
                  autoComplete="off"
                  className={input}
                />
              )}
            </Field>
            <CompanyWarning company={fields.company} />
          </div>
          <Field id="new-job-role" text="Role *" error={errors.role}>
            {(props) => (
              <input
                {...props}
                required
                value={fields.role}
                onChange={(e) => set("role")(e.target.value)}
                className={input}
              />
            )}
          </Field>
        </div>

        <Field id="new-job-url" text="Job URL" error={errors.url}>
          {(props) => (
            <input
              {...props}
              type="text"
              inputMode="url"
              value={fields.url}
              onChange={(e) => set("url")(e.target.value)}
              className={input}
            />
          )}
        </Field>

        <div className="grid gap-4 md:grid-cols-2">
          <Field id="new-job-status" text="Status" error={errors.status}>
            {(props) => (
              <select
                {...props}
                value={fields.status}
                onChange={(e) => {
                  const status = STATUSES.find((s) => s === e.target.value);
                  if (status) setFields((current) => ({ ...current, status }));
                }}
                className={input}
              >
                {STATUSES.map((status) => (
                  <option key={status} value={status}>
                    {STATUS_LABELS[status]}
                  </option>
                ))}
              </select>
            )}
          </Field>
          {fields.status === "saved" ? (
            <div />
          ) : (
            <Field
              id="new-job-applied_at"
              text="Applied on"
              error={errors.applied_at}
              hint="Leave blank for today"
            >
              {(props) => (
                <input
                  {...props}
                  type="date"
                  value={fields.applied_at}
                  onChange={(e) => set("applied_at")(e.target.value)}
                  className={input}
                />
              )}
            </Field>
          )}
          <Field id="new-job-source" text="Source" error={errors.source}>
            {(props) => (
              <select
                {...props}
                value={fields.source}
                onChange={(e) => set("source")(e.target.value)}
                className={input}
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
          <Field id="new-job-location" text="Location" error={errors.location}>
            {(props) => (
              <input
                {...props}
                value={fields.location}
                onChange={(e) => set("location")(e.target.value)}
                className={input}
              />
            )}
          </Field>
        </div>

        <details className="rounded-md border border-slate-200 bg-white px-4 py-2">
          <summary className="min-h-11 cursor-pointer py-2 font-medium">
            More details
          </summary>
          <div className="grid gap-4 pb-3 md:grid-cols-2">
            <Field id="new-job-salary" text="Salary" error={errors.salary}>
              {(props) => (
                <input
                  {...props}
                  value={fields.salary}
                  onChange={(e) => set("salary")(e.target.value)}
                  className={input}
                />
              )}
            </Field>
            <div />
            <Field
              id="new-job-contact_name"
              text="Contact name"
              error={errors.contact_name}
            >
              {(props) => (
                <input
                  {...props}
                  value={fields.contact_name}
                  onChange={(e) => set("contact_name")(e.target.value)}
                  className={input}
                />
              )}
            </Field>
            <Field
              id="new-job-contact_email"
              text="Contact email"
              error={errors.contact_email}
            >
              {(props) => (
                <input
                  {...props}
                  value={fields.contact_email}
                  onChange={(e) => set("contact_email")(e.target.value)}
                  className={input}
                />
              )}
            </Field>
            <div className="md:col-span-2">
              <Field id="new-job-notes" text="Notes" error={errors.notes}>
                {(props) => (
                  <textarea
                    {...props}
                    rows={4}
                    value={fields.notes}
                    onChange={(e) => set("notes")(e.target.value)}
                    className={`${input} py-2`}
                  />
                )}
              </Field>
            </div>
          </div>
        </details>

        <div className="flex flex-wrap gap-2 pt-2">
          <button
            type="submit"
            disabled={save.isPending}
            className="inline-flex min-h-11 items-center rounded-md bg-slate-900 px-4 font-medium text-white disabled:opacity-50"
          >
            {save.isPending ? "Saving…" : "Save job"}
          </button>
          <button
            type="button"
            onClick={cancel}
            className="inline-flex min-h-11 items-center rounded-md border border-slate-300 bg-white px-4"
          >
            Cancel
          </button>
        </div>
      </form>
    </section>
  );
}

// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// The job page's interviews: listed, added and edited inline (one form at a time), and
// deleted after a confirmation.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useRef, useState } from "react";

import { ApiError } from "../../api/client";
import {
  createInterview,
  deleteInterview,
  type Interview,
  type InterviewInput,
  listInterviews,
  updateInterview,
} from "../../api/interviews";
import type { Job } from "../../api/jobs";
import type { ErrorMeta } from "../../api/queryClient";
import { Field } from "../../components/Field";
import { validationMessages } from "../../lib/formErrors";
import {
  formatDay,
  formatWhen,
  fromLocalInput,
  MODE_LABELS,
  MODES,
  ROUND_PRESETS,
  toLocalInput,
} from "../../lib/interviews";
import { inputClass, tapTarget } from "../../lib/styles";
import { interviewsKey, useChangeStatus } from "./useChangeStatus";

const OTHER = "__other__";
type FieldName = "round_label" | "scheduled_at" | "mode" | "notes";
const FIELD_NAMES: ReadonlySet<FieldName> = new Set<FieldName>([
  "round_label",
  "scheduled_at",
  "mode",
  "notes",
]);

interface Draft {
  round: string; // "" = not set, a preset, or OTHER
  otherRound: string;
  when: string; // datetime-local value, "" = not scheduled
  mode: string; // "" = not set
  notes: string;
}

function isPreset(label: string): boolean {
  return (ROUND_PRESETS as readonly string[]).includes(label);
}

function draftFrom(interview?: Interview): Draft {
  const label = interview?.round_label ?? "";
  return {
    round: label === "" ? "" : isPreset(label) ? label : OTHER,
    otherRound: label !== "" && !isPreset(label) ? label : "",
    when: interview?.scheduled_at ? toLocalInput(interview.scheduled_at) : "",
    mode: interview?.mode ?? "",
    notes: interview?.notes ?? "",
  };
}

function bodyFrom(draft: Draft): InterviewInput {
  const label = draft.round === OTHER ? draft.otherRound.trim() : draft.round;
  return {
    round_label: label || null,
    scheduled_at: draft.when ? fromLocalInput(draft.when) : null,
    mode: MODES.find((m) => m === draft.mode) ?? null,
    notes: draft.notes.trim() || null,
  };
}

function InterviewForm({
  jobId,
  interview,
  onDone,
}: {
  jobId: string;
  interview?: Interview;
  onDone: (saved?: Interview) => void;
}) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Draft>(() => draftFrom(interview));
  const [errors, setErrors] = useState<
    Partial<Record<FieldName | "form", string>>
  >({});
  const idPrefix = `interview-${interview?.id ?? "new"}`;

  const save = useMutation({
    mutationFn: (body: InterviewInput) =>
      interview
        ? updateInterview(jobId, interview.id, body)
        : createInterview(jobId, body),
    meta: { inlineValidation: true } satisfies ErrorMeta,
    onSuccess: async (saved) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: interviewsKey(jobId) }),
        queryClient.invalidateQueries({ queryKey: ["interviews"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      ]);
      onDone(saved);
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 422) {
        setErrors(validationMessages(error, FIELD_NAMES));
      }
    },
  });

  const set = (name: keyof Draft) => (value: string) =>
    setDraft((current) => ({ ...current, [name]: value }));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setErrors({});
    save.mutate(bodyFrom(draft));
  };

  return (
    <form
      onSubmit={submit}
      aria-label={interview ? "Edit interview" : "Add interview"}
      className="space-y-3 rounded-lg border border-slate-300 bg-white p-4"
    >
      {errors.form && (
        <p role="alert" className="text-sm text-rose-700">
          {errors.form}
        </p>
      )}
      <div className="grid gap-3 md:grid-cols-2">
        <Field id={`${idPrefix}-round`} text="Round" error={errors.round_label}>
          {(props) => (
            <select
              {...props}
              value={draft.round}
              onChange={(e) => set("round")(e.target.value)}
              className={inputClass}
            >
              <option value="">Not set</option>
              {ROUND_PRESETS.map((preset) => (
                <option key={preset} value={preset}>
                  {preset}
                </option>
              ))}
              <option value={OTHER}>Other…</option>
            </select>
          )}
        </Field>
        {draft.round === OTHER && (
          <Field id={`${idPrefix}-other`} text="Round name">
            {(props) => (
              <input
                {...props}
                value={draft.otherRound}
                onChange={(e) => set("otherRound")(e.target.value)}
                className={inputClass}
              />
            )}
          </Field>
        )}
        <Field
          id={`${idPrefix}-when`}
          text="Date and time"
          hint="Leave blank if it's not scheduled yet"
          error={errors.scheduled_at}
        >
          {(props) => (
            <input
              {...props}
              type="datetime-local"
              value={draft.when}
              onChange={(e) => set("when")(e.target.value)}
              className={inputClass}
            />
          )}
        </Field>
        <Field id={`${idPrefix}-mode`} text="Mode" error={errors.mode}>
          {(props) => (
            <select
              {...props}
              value={draft.mode}
              onChange={(e) => set("mode")(e.target.value)}
              className={inputClass}
            >
              <option value="">Not set</option>
              {MODES.map((mode) => (
                <option key={mode} value={mode}>
                  {MODE_LABELS[mode]}
                </option>
              ))}
            </select>
          )}
        </Field>
      </div>
      <Field id={`${idPrefix}-notes`} text="Notes" error={errors.notes}>
        {(props) => (
          <textarea
            {...props}
            rows={3}
            value={draft.notes}
            onChange={(e) => set("notes")(e.target.value)}
            className={`${inputClass} py-2`}
          />
        )}
      </Field>
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={save.isPending}
          className={`${tapTarget} flex-1 justify-center bg-slate-900 font-medium text-white disabled:opacity-50 md:flex-none`}
        >
          {save.isPending
            ? "Saving…"
            : interview
              ? "Save interview"
              : "Add interview"}
        </button>
        <button
          type="button"
          onClick={() => onDone()}
          className={`${tapTarget} flex-1 justify-center border border-slate-300 bg-white md:flex-none`}
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

function describe(interview: Interview): string {
  const round = interview.round_label ?? "interview";
  if (!interview.scheduled_at) return `the ${round} (not yet scheduled)`;
  return `the ${round} on ${formatDay(interview.scheduled_at)}`;
}

function InterviewCard({
  interview,
  onEdit,
  onDelete,
}: {
  interview: Interview;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const past =
    interview.scheduled_at !== null &&
    new Date(interview.scheduled_at) < new Date();
  return (
    <li
      className={`rounded-lg border border-slate-200 p-4 ${past ? "bg-slate-50 text-slate-500" : "bg-white"}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-medium">
            {interview.round_label ?? "Interview"}
            {past && <span className="ml-2 text-xs font-normal">(past)</span>}
          </p>
          <p className="text-sm">
            {interview.scheduled_at
              ? formatWhen(interview.scheduled_at)
              : "Not yet scheduled"}
            {interview.mode && ` · ${MODE_LABELS[interview.mode]}`}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onEdit}
            aria-label={`Edit ${describe(interview)}`}
            className={`${tapTarget} border border-slate-300 bg-white text-slate-700`}
          >
            Edit
          </button>
          <button
            type="button"
            onClick={onDelete}
            aria-label={`Delete ${describe(interview)}`}
            className={`${tapTarget} border border-rose-300 bg-white text-rose-700`}
          >
            Delete
          </button>
        </div>
      </div>
      {interview.notes && (
        <p className="mt-2 text-sm whitespace-pre-line">{interview.notes}</p>
      )}
    </li>
  );
}

export function Interviews({ job }: { job: Job }) {
  const queryClient = useQueryClient();
  const changeStatus = useChangeStatus(job.id);
  const { data: interviews, isPending } = useQuery({
    queryKey: interviewsKey(job.id),
    queryFn: () => listInterviews(job.id),
  });
  // Which form is open: "new", an interview's id, or none. One at a time.
  const [editing, setEditing] = useState<string | null>(null);
  const [suggestInterviewing, setSuggestInterviewing] = useState(false);
  const [deleting, setDeleting] = useState<Interview | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);

  const remove = useMutation({
    mutationFn: (interview: Interview) => deleteInterview(job.id, interview.id),
    onSuccess: async () => {
      dialog.current?.close();
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: interviewsKey(job.id) }),
        queryClient.invalidateQueries({ queryKey: ["interviews"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      ]);
    },
  });

  const confirmDelete = (interview: Interview) => {
    setDeleting(interview);
    dialog.current?.showModal();
  };

  return (
    <section aria-labelledby="interviews-heading" className="mt-8">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="interviews-heading" className="text-lg font-semibold">
          Interviews
        </h2>
        {editing !== "new" && (
          <button
            type="button"
            onClick={() => {
              setEditing("new");
              setSuggestInterviewing(false);
            }}
            className={`${tapTarget} border border-slate-300 bg-white`}
          >
            Add interview
          </button>
        )}
      </div>

      {suggestInterviewing && (
        <div className="mt-3 flex flex-col gap-2 rounded-md bg-violet-50 px-4 py-3 text-violet-900 md:flex-row md:items-center">
          <p className="md:mr-auto">Move this job to Interviewing?</p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => {
                changeStatus.mutate("interviewing");
                setSuggestInterviewing(false);
              }}
              className={`${tapTarget} flex-1 justify-center bg-violet-800 font-medium text-white md:flex-none`}
            >
              Yes
            </button>
            <button
              type="button"
              onClick={() => setSuggestInterviewing(false)}
              className={`${tapTarget} flex-1 justify-center border border-violet-300 bg-white md:flex-none`}
            >
              Not now
            </button>
          </div>
        </div>
      )}

      <div className="mt-3 space-y-3">
        {editing === "new" && (
          <InterviewForm
            jobId={job.id}
            onDone={(saved) => {
              setEditing(null);
              // Never automatic: just offered, for jobs that haven't got that far yet.
              if (
                saved &&
                (job.status === "saved" || job.status === "applied")
              ) {
                setSuggestInterviewing(true);
              }
            }}
          />
        )}
        {isPending ? (
          <div className="h-16 animate-pulse rounded-lg bg-slate-200" />
        ) : interviews && interviews.length > 0 ? (
          <ul className="space-y-3">
            {interviews.map((interview) =>
              editing === interview.id ? (
                <li key={interview.id}>
                  <InterviewForm
                    jobId={job.id}
                    interview={interview}
                    onDone={() => setEditing(null)}
                  />
                </li>
              ) : (
                <InterviewCard
                  key={interview.id}
                  interview={interview}
                  onEdit={() => setEditing(interview.id)}
                  onDelete={() => confirmDelete(interview)}
                />
              ),
            )}
          </ul>
        ) : (
          editing !== "new" && (
            <p className="text-slate-600">No interviews yet.</p>
          )
        )}
      </div>

      <dialog
        ref={dialog}
        aria-labelledby="delete-interview-heading"
        className="m-auto max-w-md rounded-lg p-6 backdrop:bg-slate-900/50"
      >
        <h2 id="delete-interview-heading" className="text-lg font-semibold">
          Delete this interview?
        </h2>
        <p className="mt-2 text-slate-700">
          Delete {deleting ? describe(deleting) : "this interview"}? This can't
          be undone.
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
            onClick={() => deleting && remove.mutate(deleting)}
            disabled={remove.isPending}
            className={`${tapTarget} bg-rose-700 font-medium text-white disabled:opacity-50`}
          >
            {remove.isPending ? "Deleting…" : "Delete interview"}
          </button>
        </div>
      </dialog>
    </section>
  );
}

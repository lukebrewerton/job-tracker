// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import type { ReactNode } from "react";

import { labelClass } from "../lib/styles";

export interface ControlProps {
  id: string;
  "aria-invalid": boolean;
  "aria-describedby"?: string;
}

/** A labelled form control, with an optional hint and error wired up for screen readers. */
export function Field({
  id,
  text,
  error,
  hint,
  children,
}: {
  id: string;
  text: string;
  error?: string;
  hint?: string;
  children: (props: ControlProps) => ReactNode;
}) {
  const describedBy = [error && `${id}-error`, hint && `${id}-hint`]
    .filter(Boolean)
    .join(" ");
  return (
    <div>
      <label htmlFor={id} className={labelClass}>
        {text}
      </label>
      {children({
        id,
        "aria-invalid": Boolean(error),
        "aria-describedby": describedBy || undefined,
      })}
      {hint && (
        <p id={`${id}-hint`} className="mt-1 text-xs text-slate-500">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} className="mt-1 text-sm text-rose-700">
          {error}
        </p>
      )}
    </div>
  );
}

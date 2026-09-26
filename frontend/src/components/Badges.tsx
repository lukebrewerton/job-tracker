// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import {
  ATTENTION_LABELS,
  type Attention,
  type JobStatus,
  STATUS_LABELS,
} from "../lib/format";
import { ATTENTION_STYLE, STATUS_BADGE } from "../lib/styles";

export function StatusBadge({ status }: { status: JobStatus }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_BADGE[status]}`}
    >
      {STATUS_LABELS[status]}
    </span>
  );
}

export function AttentionLabel({ attention }: { attention: Attention | null }) {
  if (!attention) return null;
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${ATTENTION_STYLE[attention].label}`}
    >
      {ATTENTION_LABELS[attention]}
    </span>
  );
}

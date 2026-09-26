// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import type { ApiError } from "../api/client";

/**
 * A 422's messages by field name, for showing under each field rather than as a toast.
 * Messages for anything not in `fields` (or not tied to a field) go under "form".
 */
export function validationMessages<F extends string>(
  error: ApiError,
  fields: ReadonlySet<F>,
): Partial<Record<F | "form", string>> {
  const messages: Partial<Record<F | "form", string>> = {};
  const body = error.body;
  if (
    !body ||
    typeof body !== "object" ||
    !("detail" in body) ||
    !Array.isArray(body.detail)
  ) {
    messages.form = error.message;
    return messages;
  }
  const detail: unknown[] = body.detail;
  const isField = (value: unknown): value is F =>
    typeof value === "string" && (fields as ReadonlySet<string>).has(value);
  for (const item of detail) {
    if (
      !item ||
      typeof item !== "object" ||
      !("msg" in item) ||
      !("loc" in item)
    )
      continue;
    const { loc, msg } = item;
    if (typeof msg !== "string" || !Array.isArray(loc)) continue;
    const field: unknown = loc[1];
    messages[isField(field) ? field : "form"] ??= msg;
  }
  return messages;
}

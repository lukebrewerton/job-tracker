// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Web storage that never throws: private windows and blocked storage just behave
// as if nothing was saved. localStorage by default; sessionStorage (this tab only)
// where asked.

type Scope = "local" | "session";

function store(scope: Scope): Storage {
  return scope === "session" ? window.sessionStorage : window.localStorage;
}

export function readItem(key: string, scope: Scope = "local"): string | null {
  try {
    return store(scope).getItem(key);
  } catch {
    return null;
  }
}

export function writeItem(
  key: string,
  value: string,
  scope: Scope = "local",
): void {
  try {
    store(scope).setItem(key, value);
  } catch {
    // Not available: the view just isn't remembered.
  }
}

export function removeItem(key: string, scope: Scope = "local"): void {
  try {
    store(scope).removeItem(key);
  } catch {
    // Nothing to remove.
  }
}

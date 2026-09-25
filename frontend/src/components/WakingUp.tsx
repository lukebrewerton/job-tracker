// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { useIsFetching, useIsMutating } from "@tanstack/react-query";
import { useEffect, useState } from "react";

export const WAKING_UP_AFTER_MS = 2000;

/**
 * Shown once any request has been pending for a couple of seconds: usually the server
 * or the database waking from idle. Every API call goes through TanStack Query, so its
 * counters see them all.
 */
export function WakingUp({
  afterMs = WAKING_UP_AFTER_MS,
}: {
  afterMs?: number;
}) {
  const busy = useIsFetching() + useIsMutating() > 0;
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    if (!busy) return () => {};
    const timer = setTimeout(() => setSlow(true), afterMs);
    return () => {
      clearTimeout(timer);
      setSlow(false);
    };
  }, [busy, afterMs]);

  if (!slow) return null;
  return (
    <output className="fixed inset-x-0 bottom-4 z-50 mx-auto block w-fit rounded-full bg-slate-900 px-4 py-2 text-sm text-white shadow-lg">
      Waking up… this can take a few seconds.
    </output>
  );
}

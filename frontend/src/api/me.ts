// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { api, ApiError, navigation } from "./client";
import type { components } from "./schema";

export type Me = components["schemas"]["Me"];

export const meQueryKey = ["me"] as const;

/** The signed-in user, or null when signed out (a 401 here isn't an error). */
export function useMe() {
  return useQuery({
    queryKey: meQueryKey,
    queryFn: async (): Promise<Me | null> => {
      const { data, error, response } = await api.GET("/api/me");
      if (response.status === 401) return null;
      if (!response.ok || !data) throw new ApiError(response.status, error);
      return data;
    },
    staleTime: 5 * 60 * 1000,
  });
}

export function browserTimezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

/**
 * Keep the stored time zone in step with the browser's: the server uses it for dates it
 * decides itself ("today", the dashboard's day boundaries). No setting to manage; it
 * follows the user if they move or travel. A zone the server doesn't know is logged and
 * ignored, not shown: it changes nothing the user can act on.
 */
export function useTimezoneSync(me: Me | null | undefined): void {
  const queryClient = useQueryClient();
  const timezone = browserTimezone();

  useEffect(() => {
    if (!me || me.timezone === timezone) return;
    void (async () => {
      const { response } = await api.PUT("/api/me/timezone", {
        body: { timezone },
      });
      if (response.ok) {
        await queryClient.invalidateQueries({ queryKey: meQueryKey });
      } else {
        console.warn(
          `Time zone ${timezone} not saved (HTTP ${response.status})`,
        );
      }
    })();
  }, [me, timezone, queryClient]);
}

/** Sign out, then land on the public front page (not the sign-in page, which would
 *  sign straight back in through the identity provider). */
export async function logout(): Promise<void> {
  const response = await fetch("/auth/logout", { method: "POST" });
  if (!response.ok) throw new ApiError(response.status, null);
  navigation.assign("/?signed_out=1");
}

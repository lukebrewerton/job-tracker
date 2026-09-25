// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { useQuery } from "@tanstack/react-query";
import { act, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { withQueryClient } from "../test/utils";
import { WakingUp } from "./WakingUp";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

function SlowQuery({ until }: { until: Promise<string> }) {
  useQuery({ queryKey: ["slow"], queryFn: () => until });
  return null;
}

it("appears once a request has been pending for 2 seconds, and goes when it's done", async () => {
  let finish!: (value: string) => void;
  const until = new Promise<string>((resolve) => (finish = resolve));
  withQueryClient(
    <>
      <SlowQuery until={until} />
      <WakingUp />
    </>,
  );

  await act(() => vi.advanceTimersByTimeAsync(1999));
  expect(screen.queryByText(/waking up/i)).not.toBeInTheDocument();

  await act(() => vi.advanceTimersByTimeAsync(1));
  expect(screen.getByText(/waking up/i)).toBeInTheDocument();

  await act(async () => {
    finish("done");
    await vi.runAllTimersAsync();
  });
  expect(screen.queryByText(/waking up/i)).not.toBeInTheDocument();
});

it("never appears for a quick request", async () => {
  withQueryClient(
    <>
      <SlowQuery until={Promise.resolve("quick")} />
      <WakingUp />
    </>,
  );
  await act(() => vi.advanceTimersByTimeAsync(5000));
  expect(screen.queryByText(/waking up/i)).not.toBeInTheDocument();
});

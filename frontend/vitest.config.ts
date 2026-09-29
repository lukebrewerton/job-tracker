// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { defineConfig, mergeConfig } from "vitest/config";

import viteConfig from "./vite.config";

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: "jsdom",
      // A fixed zone with daylight saving, so date/time tests mean the same everywhere.
      env: { TZ: "Europe/London" },
      setupFiles: ["./src/test/setup.ts"],
      restoreMocks: true,
    },
  }),
);

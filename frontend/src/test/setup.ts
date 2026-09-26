// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import { navigation } from "../api/client";

afterEach(() => {
  cleanup();
  navigation.leaving = false;
  window.history.replaceState(null, "", "/");
});

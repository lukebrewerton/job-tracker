// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Forward API and auth calls to FastAPI (`make dev`) so the browser only ever
    // talks to one origin, as in production. changeOrigin stays false so the backend
    // sees the browser's Host, and its canonical-host redirect behaves as in prod.
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: false },
      "/auth": { target: "http://localhost:8000", changeOrigin: false },
    },
  },
});

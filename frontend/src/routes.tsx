// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import type { RouteObject } from "react-router";

import { Layout } from "./components/Layout";
import { Home } from "./pages/Home";
import { NotFound } from "./pages/NotFound";
import { JobsPage } from "./pages/jobs/JobsPage";
import { NewJobPage } from "./pages/newjob/NewJobPage";
import { JobDetailPage } from "./pages/jobdetail/JobDetailPage";
import { Dashboard, Interviews } from "./pages/Placeholder";

// Only "/" works signed out; the server sends every other page to sign in first
// (app/spa.py), and the API client does the same on a 401.
export const routes: RouteObject[] = [
  {
    element: <Layout />,
    children: [
      { index: true, element: <Home /> },
      { path: "dashboard", element: <Dashboard /> },
      { path: "jobs", element: <JobsPage /> },
      { path: "jobs/new", element: <NewJobPage /> },
      { path: "jobs/:id", element: <JobDetailPage /> },
      { path: "interviews", element: <Interviews /> },
      { path: "*", element: <NotFound /> },
    ],
  },
];

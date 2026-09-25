// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { createBrowserRouter, RouterProvider } from "react-router";
import { Toaster } from "sonner";

import { createQueryClient } from "./api/queryClient";
import { WakingUp } from "./components/WakingUp";
import { routes } from "./routes";

const router = createBrowserRouter(routes);

export default function App() {
  const [queryClient] = useState(createQueryClient);
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <WakingUp />
      <Toaster position="top-center" richColors closeButton />
    </QueryClientProvider>
  );
}

// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { Link } from "react-router";

export function NotFound() {
  return (
    <section className="py-8 text-center">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="mt-2 text-slate-600">There's nothing at this address.</p>
      <Link
        to="/"
        className="mt-6 inline-flex min-h-11 items-center rounded-md bg-slate-900 px-4 font-medium text-white"
      >
        Go to the front page
      </Link>
    </section>
  );
}

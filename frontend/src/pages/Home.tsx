// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { Link, useSearchParams } from "react-router";

import { useMe } from "../api/me";
import { NAV_LINKS, SIGN_IN_URL } from "../nav";

const button = "inline-flex min-h-11 items-center rounded-md px-4 font-medium";

/** The public front page: what this is, and a way in. Also where logout lands. */
export function Home() {
  const { data: me, isPending } = useMe();
  const [params] = useSearchParams();
  const signedOut = params.get("signed_out") === "1";

  return (
    <section className="mx-auto max-w-xl py-8 text-center">
      <h1 className="text-3xl font-semibold">Job Tracker</h1>
      <p className="mt-3 text-slate-600">
        Keep track of the jobs you've saved, applied for and interviewed for,
        and see what needs following up.
      </p>

      {signedOut && !me && (
        <output className="mt-6 block rounded-md bg-slate-100 px-4 py-2 text-slate-700">
          You've signed out.
        </output>
      )}

      <div className="mt-8">
        {isPending ? (
          <div className="mx-auto h-11 w-40 animate-pulse rounded-md bg-slate-200" />
        ) : me ? (
          <>
            <p className="text-slate-600">
              Signed in as{" "}
              <span className="font-medium text-slate-900">{me.email}</span>
            </p>
            <nav
              aria-label="Go to"
              className="mt-4 flex flex-wrap justify-center gap-2"
            >
              {NAV_LINKS.map(({ to, label }) => (
                <Link
                  key={to}
                  to={to}
                  className={`${button} bg-slate-900 text-white`}
                >
                  {label}
                </Link>
              ))}
            </nav>
          </>
        ) : (
          <a href={SIGN_IN_URL} className={`${button} bg-slate-900 text-white`}>
            Sign in
          </a>
        )}
      </div>
    </section>
  );
}

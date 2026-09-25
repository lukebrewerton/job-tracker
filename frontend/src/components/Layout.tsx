// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { useEffect, useId, useRef, useState } from "react";
import { Link, NavLink, Outlet } from "react-router";
import { toast } from "sonner";

import { logout, useMe, useTimezoneSync } from "../api/me";
import { NAV_LINKS, SIGN_IN_URL } from "../nav";

// At least 44px tall: comfortable touch targets.
const target = "inline-flex min-h-11 items-center rounded-md px-3";
const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `${target} ${isActive ? "bg-slate-200 font-medium text-slate-900" : "text-slate-600 hover:bg-slate-100"}`;

function useLogout() {
  const [pending, setPending] = useState(false);
  return {
    pending,
    signOut: async () => {
      setPending(true);
      try {
        await logout();
      } catch {
        toast.error("Couldn't sign out. Please try again.");
        setPending(false);
      }
    },
  };
}

export function Layout() {
  const { data: me } = useMe();
  useTimezoneSync(me);
  const { pending, signOut } = useLogout();

  const [menuOpen, setMenuOpen] = useState(false);
  const menuId = useId();
  const menuButton = useRef<HTMLButtonElement>(null);
  const menuPanel = useRef<HTMLDivElement>(null);
  const closeMenu = () => setMenuOpen(false);

  // While open: focus its first link; Escape or a tap outside closes it.
  useEffect(() => {
    if (!menuOpen) return () => {};
    menuPanel.current?.querySelector<HTMLElement>("a, button")?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
        menuButton.current?.focus();
      }
    };
    const onPointer = (event: PointerEvent) => {
      const inside =
        event.target instanceof Node &&
        menuPanel.current?.contains(event.target);
      const onButton =
        event.target instanceof Node &&
        menuButton.current?.contains(event.target);
      if (!inside && !onButton) setMenuOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [menuOpen]);

  const signedIn = Boolean(me);

  return (
    <div className="min-h-dvh bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center gap-2 px-4 py-2">
          <Link
            to="/"
            onClick={closeMenu}
            className={`${target} -ml-3 text-lg font-semibold`}
          >
            Job Tracker
          </Link>

          {signedIn && (
            <nav aria-label="Main" className="hidden md:flex md:gap-1">
              {NAV_LINKS.map(({ to, label }) => (
                <NavLink key={to} to={to} className={navLinkClass}>
                  {label}
                </NavLink>
              ))}
            </nav>
          )}

          <div className="ml-auto flex items-center gap-2">
            {signedIn ? (
              <>
                <Link
                  to="/jobs/new"
                  onClick={closeMenu}
                  className={`${target} bg-slate-900 font-medium text-white hover:bg-slate-700`}
                >
                  New job
                </Link>
                <span className="hidden text-sm text-slate-600 md:inline">
                  {me?.email}
                </span>
                <button
                  type="button"
                  onClick={() => void signOut()}
                  disabled={pending}
                  className={`${target} hidden text-slate-600 hover:bg-slate-100 disabled:opacity-50 md:inline-flex`}
                >
                  {pending ? "Signing out…" : "Log out"}
                </button>
                <button
                  ref={menuButton}
                  type="button"
                  aria-expanded={menuOpen}
                  aria-controls={menuId}
                  onClick={() => setMenuOpen((open) => !open)}
                  className={`${target} gap-2 border border-slate-300 md:hidden`}
                >
                  <span aria-hidden="true">☰</span> Menu
                </button>
              </>
            ) : (
              me === null && (
                <a
                  href={SIGN_IN_URL}
                  className={`${target} bg-slate-900 font-medium text-white`}
                >
                  Sign in
                </a>
              )
            )}
          </div>
        </div>

        {signedIn && menuOpen && (
          <div
            ref={menuPanel}
            id={menuId}
            className="border-t border-slate-200 bg-white px-4 py-2 md:hidden"
          >
            <nav aria-label="Main" className="flex flex-col">
              {NAV_LINKS.map(({ to, label }) => (
                <NavLink
                  key={to}
                  to={to}
                  className={navLinkClass}
                  onClick={closeMenu}
                >
                  {label}
                </NavLink>
              ))}
            </nav>
            <div className="mt-2 flex items-center justify-between border-t border-slate-200 pt-2">
              <span className="truncate text-sm text-slate-600">
                {me?.email}
              </span>
              <button
                type="button"
                onClick={() => void signOut()}
                disabled={pending}
                className={`${target} text-slate-600 hover:bg-slate-100 disabled:opacity-50`}
              >
                {pending ? "Signing out…" : "Log out"}
              </button>
            </div>
          </div>
        )}
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}

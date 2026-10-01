// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later

/**
 * The footer's links: the manual and the source code. The server puts them in the page as
 * <meta> tags (DOCS_URL and SOURCE_URL; see app/spa.py), so they're there even signed out.
 * Missing only when the page isn't served by the app, e.g. Vite's dev server on :5173.
 */
export function aboutLinks(): { docsUrl?: string; sourceUrl?: string } {
  const meta = (name: string) =>
    document.querySelector<HTMLMetaElement>(`meta[name="${name}"]`)?.content ||
    undefined;
  return { docsUrl: meta("jt-docs-url"), sourceUrl: meta("jt-source-url") };
}

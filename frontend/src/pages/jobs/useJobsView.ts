// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// The jobs table's view (filter, search, sort, page size, page), kept in the URL so it
// can be bookmarked and the back button works. The last view is also saved, so a bare
// /jobs restores it (except the page number, which always starts at 1).
import { useEffect } from "react";
import { useSearchParams } from "react-router";

import type { JobListQuery } from "../../api/jobs";
import { STATUSES } from "../../lib/format";
import { readItem, removeItem, writeItem } from "../../lib/storage";

export type StatusFilter = NonNullable<JobListQuery["status"]>;
export type SortField = NonNullable<JobListQuery["sort"]>;
export type SortOrder = "asc" | "desc";
export const PAGE_SIZES = [25, 50, 100] as const;
export type PageSize = (typeof PAGE_SIZES)[number];

export interface JobsView {
  status: StatusFilter;
  q: string;
  sort: SortField;
  order: SortOrder;
  size: PageSize;
  page: number;
}

export const DEFAULT_VIEW: JobsView = {
  status: "active",
  q: "",
  sort: "created_at",
  order: "desc",
  size: 25,
  page: 1,
};

export const STORAGE_KEY = "job-tracker.jobs-view";

const STATUS_FILTERS: readonly StatusFilter[] = ["active", "all", ...STATUSES];
const SORT_FIELDS: readonly SortField[] = [
  "company",
  "role",
  "status",
  "last_status_change",
  "applied_at",
  "created_at",
];

function isStatusFilter(value: string): value is StatusFilter {
  return (STATUS_FILTERS as readonly string[]).includes(value);
}

function isSortField(value: string): value is SortField {
  return (SORT_FIELDS as readonly string[]).includes(value);
}

export function isPageSize(value: number): value is PageSize {
  return (PAGE_SIZES as readonly number[]).includes(value);
}

/** Read a view from query parameters, ignoring anything invalid. */
export function parseView(params: URLSearchParams): JobsView {
  const status = params.get("status") ?? "";
  const sort = params.get("sort") ?? "";
  const order = params.get("order");
  const size = Number(params.get("size"));
  const page = Number(params.get("page"));
  return {
    status: isStatusFilter(status) ? status : DEFAULT_VIEW.status,
    q: params.get("q") ?? "",
    sort: isSortField(sort) ? sort : DEFAULT_VIEW.sort,
    order: order === "asc" || order === "desc" ? order : DEFAULT_VIEW.order,
    size: isPageSize(size) ? size : DEFAULT_VIEW.size,
    page: Number.isInteger(page) && page > 1 ? page : 1,
  };
}

/** Query parameters for a view, leaving out anything at its default. */
export function viewParams(
  view: JobsView,
  { withPage = true } = {},
): URLSearchParams {
  const params = new URLSearchParams();
  if (view.status !== DEFAULT_VIEW.status) params.set("status", view.status);
  if (view.q) params.set("q", view.q);
  if (view.sort !== DEFAULT_VIEW.sort) params.set("sort", view.sort);
  if (view.order !== DEFAULT_VIEW.order) params.set("order", view.order);
  if (view.size !== DEFAULT_VIEW.size) params.set("size", String(view.size));
  if (withPage && view.page > 1) params.set("page", String(view.page));
  return params;
}

export function useJobsView() {
  const [searchParams, setSearchParams] = useSearchParams();

  // A bare /jobs shows the saved view straight away (no flash of the defaults), and the
  // URL is then updated to match.
  const bare = searchParams.toString() === "";
  const saved = bare ? readItem(STORAGE_KEY) : null;
  const effective = saved ? new URLSearchParams(saved) : searchParams;
  const view = parseView(effective);

  useEffect(() => {
    if (saved) setSearchParams(new URLSearchParams(saved), { replace: true });
  }, [saved, setSearchParams]);

  // Remember everything but the page number.
  const remembered = viewParams(view, { withPage: false }).toString();
  useEffect(() => {
    if (remembered) writeItem(STORAGE_KEY, remembered);
    else removeItem(STORAGE_KEY);
  }, [remembered]);

  /** Change the view. Anything but a page change goes back to page 1. */
  const update = (changes: Partial<JobsView>) => {
    const next = { ...view, ...changes };
    if (!("page" in changes)) next.page = 1;
    const params = viewParams(next);
    // Back to the defaults: forget the saved view first, or the bare /jobs this leaves
    // would restore it straight away.
    if (params.toString() === "") removeItem(STORAGE_KEY);
    setSearchParams(params);
  };

  const reset = () => {
    removeItem(STORAGE_KEY);
    setSearchParams(new URLSearchParams());
  };

  return { view, update, reset };
}

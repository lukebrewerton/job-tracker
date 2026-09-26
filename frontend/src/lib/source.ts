// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import type { components } from "../api/schema";

export type JobSource = components["schemas"]["JobSource"];

export const SOURCE_LABELS: Record<JobSource, string> = {
  linkedin: "LinkedIn",
  company_site: "Company site",
  referral: "Referral",
  recruiter: "Recruiter",
  indeed: "Indeed",
  other: "Other",
};

export const SOURCES: readonly JobSource[] = [
  "linkedin",
  "company_site",
  "referral",
  "recruiter",
  "indeed",
  "other",
];

// Applicant-tracking systems that host a company's own job pages.
const COMPANY_SITE_HOSTS = [
  "greenhouse.io",
  "lever.co",
  "myworkdayjobs.com",
  "ashbyhq.com",
  "smartrecruiters.com",
  "workable.com",
];

function isOrUnder(host: string, domain: string): boolean {
  return host === domain || host.endsWith(`.${domain}`);
}

/** The source when the URL makes it obvious; otherwise null, for the user to choose. */
export function inferSource(url: string): JobSource | null {
  let host: string;
  try {
    host = new URL(url).hostname.toLowerCase();
  } catch {
    return null;
  }
  if (isOrUnder(host, "linkedin.com")) return "linkedin";
  // indeed.com, uk.indeed.com, indeed.co.uk, de.indeed.com …
  if (/(^|\.)indeed\.[a-z.]+$/.test(host)) return "indeed";
  if (COMPANY_SITE_HOSTS.some((domain) => isOrUnder(host, domain)))
    return "company_site";
  return null;
}

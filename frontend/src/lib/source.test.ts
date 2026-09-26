// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";

import { inferSource } from "./source";

describe("inferSource", () => {
  it.each([
    ["https://www.linkedin.com/jobs/view/4012345678/", "linkedin"],
    ["https://uk.linkedin.com/jobs/view/1", "linkedin"],
    ["https://uk.indeed.com/viewjob?jk=abc", "indeed"],
    ["https://www.indeed.co.uk/viewjob?jk=abc", "indeed"],
    ["https://boards.greenhouse.io/acme/jobs/1", "company_site"],
    ["https://jobs.lever.co/acme/123", "company_site"],
    ["https://acme.wd3.myworkdayjobs.com/en-GB/Careers/job/1", "company_site"],
    ["https://jobs.ashbyhq.com/acme/1", "company_site"],
  ])("%s is %s", (url, source) => {
    expect(inferSource(url)).toBe(source);
  });

  it.each([
    "https://careers.acme.test/jobs/42", // could be anything: the user chooses
    "https://notlinkedin.com/jobs/1", // look-alike host
    "https://linkedin.com.evil.test/jobs/1",
    "not a url",
    "",
  ])("%s is left for the user", (url) => {
    expect(inferSource(url)).toBeNull();
  });
});

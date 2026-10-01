// Copyright (C) 2026 Luke Brewerton
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// The Job Tracker manual: https://job-tracker-docs.job-finder.dev (Starlight, deployed to GitHub Pages
// by .github/workflows/docs.yml). Pages are Markdown in src/content/docs/.
import starlight from "@astrojs/starlight";
import { defineConfig } from "astro/config";
import starlightLinksValidator from "starlight-links-validator";

export default defineConfig({
  site: "https://job-tracker-docs.job-finder.dev",
  integrations: [
    starlight({
      title: "Job Tracker",
      description:
        "A self-hostable job application tracker: the user and self-hosting manual.",
      logo: { src: "./src/assets/logo.svg" },
      favicon: "/favicon.svg",
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/lukebrewerton/job-tracker",
        },
      ],
      editLink: {
        baseUrl: "https://github.com/lukebrewerton/job-tracker/edit/main/docs/",
      },
      // A broken internal link fails the build (and so the PR).
      plugins: [starlightLinksValidator()],
      sidebar: [
        {
          label: "Using Job Tracker",
          items: [
            "using/getting-started",
            "using/dashboard",
            "using/jobs",
            "using/adding-a-job",
            "using/job-page",
            "using/interviews",
            "using/browser-extension",
          ],
        },
        {
          label: "Self-hosting",
          items: [
            "self-hosting/deploying",
            "self-hosting/configuration",
            "self-hosting/custom-domain",
            "self-hosting/backups",
          ],
        },
        {
          label: "Development",
          items: [
            "development/local-development",
            "development/secret-scanning",
          ],
        },
        {
          label: "API",
          items: ["api/versions-and-releases", "api/generating-a-client"],
        },
        { label: "About", items: ["about/licence-and-branding"] },
      ],
    }),
  ],
});

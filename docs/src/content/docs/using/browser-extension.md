---
title: Browser extension
description: Saving a job from its posting with one click, in Firefox.
---

The Firefox extension adds a Job Tracker button to the toolbar. On a job posting, select it
and your instance's [new job form](/using/adding-a-job/#starting-from-a-posting) opens in a
new tab, with the posting's link and title already filled in.

It's a link opener, nothing more: it reads the current tab's address and title when you select
the button, and asks for no other access. It stores no passwords and never contacts your
instance itself. The form opens in your browser as usual, signed in as you.

## Installing it

You need Firefox 142 or newer. The extension is signed by Mozilla but isn't listed on
addons.mozilla.org, so it's installed from its GitHub releases:

1. Open the [latest release](https://github.com/lukebrewerton/job-tracker-extension/releases/latest)
   and select the `job-tracker-<version>.xpi` file.
2. Firefox asks whether to add Job Tracker. Choose **Add**.

   If the file downloads instead, open `about:addons`, select the cog, choose
   **Install Add-on From File…** and pick the file.
3. To keep the button in view, pin it: open the extensions menu (the jigsaw piece) and choose
   **Pin to Toolbar** next to Job Tracker.

Firefox keeps the extension up to date from then on.

## Setting it up

The first time you select the button, it opens its settings. You can also get there from
`about:addons` → **Job Tracker** → **Preferences**.

Enter the address you sign in to Job Tracker at, such as `https://jobs.example.com`, and
choose **Save**. Only the address itself is kept: anything after it, like `/dashboard`, is
dropped. It has to be an `https://` address, except `http://localhost` for a
[development instance](/development/local-development/). **Open Job Tracker** checks it's
the right one. If you use Firefox sync, the setting follows you to your other computers.

## Using it

On a job posting, select the Job Tracker button. The new job form opens next to the posting,
filled in from the tab:

- **Job URL** is the posting's address, and **Source** is worked out from it.
- **Role** is the tab's title, for you to tidy up.
- On **LinkedIn**, the title (`Role | Company | LinkedIn`) gives the role and the
  **Company** too.
- On **Indeed**, the title (`Role - Location - Indeed`) gives the role.
- A job selected in **LinkedIn or Indeed search results** is saved with the job's own
  address, not the search's, so the link still leads to it later. Indeed's search page has no
  useful title, so **Role** is left for you to fill in.

On a page that isn't a website, such as a new tab, the button opens an empty form. If you're
signed out, you sign in first and then land on the filled-in form.

---
title: Backups
description: Optional nightly, encrypted, restore-checked backups to any S3-compatible bucket.
---

Optional, and off until you configure it. A scheduled GitHub Actions workflow
(`.github/workflows/backup.yml`) backs the database up every night:

1. `pg_dump` (custom format, zstd-compressed), without session rows;
2. restores the dump into a throwaway Postgres in the same run and compares row counts,
   so a backup that can't be restored fails loudly instead of being kept;
3. encrypts it with [age](https://age-encryption.org) to your public key;
4. uploads it to any S3-compatible bucket (Cloudflare R2, AWS S3, Backblaze B2, MinIO…),
   under `daily/`, and on the 1st of the month under `monthly/` too.

The job is skipped unless the `BACKUP_BUCKET` variable is set. Don't want backups? Don't
set it. There's nothing to delete or disable.

## Setting it up

1. **A key pair.** `brew install age`, then `age-keygen -o job-tracker-backup.key`. It
   prints the public key (`age1…`). Keep the key file somewhere safe, such as a password
   manager: without it, the backups can't be decrypted. It never goes to GitHub.
2. **A read-only database role.** Connected as your Neon project's owner role (e.g.
   `neondb_owner`, via `psql` or a database client, using a direct connection), with your
   own password and the name of your app's role. Not the Neon SQL Editor: it runs as the
   database's owner, which is your app role, and that can't create roles.

   ```sql
   CREATE ROLE jobtracker_backup LOGIN PASSWORD '<a long random password>'
     NOSUPERUSER BYPASSRLS NOCREATEDB NOCREATEROLE;
   -- The app role owns the tables, so the grants are made as it.
   GRANT <app_role> TO CURRENT_USER;
   SET ROLE <app_role>;
   GRANT USAGE ON SCHEMA public TO jobtracker_backup;
   GRANT SELECT ON ALL TABLES IN SCHEMA public TO jobtracker_backup;
   GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO jobtracker_backup;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO jobtracker_backup;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON SEQUENCES TO jobtracker_backup;
   RESET ROLE;
   REVOKE <app_role> FROM CURRENT_USER;
   ```

   `BYPASSRLS` is needed: without it `pg_dump` can't read tables that have row-level
   security. The role can only read. Use its **direct** (non-pooled) connection string.
3. **A bucket.** For Cloudflare R2: create a bucket, then add
   - lifecycle rules: delete objects under `daily/` after 35 days, and under `monthly/`
     after 395 days (13 months);
   - a bucket lock rule: objects can't be deleted within 7 days of upload;
   - an API token with **Object Read & Write** on that bucket only.

   Other providers have equivalents (S3 lifecycle rules and Object Lock, for example).
4. **GitHub.** In the repo's settings:
   - Environments → New environment `backup` → deployment branches: `main` only. Add
     the secrets `BACKUP_DATABASE_URL` (the role's connection string),
     `BACKUP_S3_ACCESS_KEY_ID` and `BACKUP_S3_SECRET_ACCESS_KEY`.
   - Secrets and variables → Actions → Variables (repository): `BACKUP_BUCKET`,
     `BACKUP_AGE_RECIPIENT` (the `age1…` public key), `BACKUP_S3_ENDPOINT` (for R2,
     `https://<account id>.r2.cloudflarestorage.com`; leave unset for AWS S3), and
     optionally `BACKUP_S3_REGION` (defaults to `auto`, which R2 wants).
5. **Try it.** Actions → Backup → Run workflow. The run's summary shows the file and its
   row counts.

GitHub pauses scheduled workflows in a public repo after 60 days without activity; it
emails you, and one click re-enables it.

## Restoring

Download a backup from the bucket, then, with local Postgres running (`make up`):

```sh
make restore FILE=job-tracker-2026-09-30T0217Z.dump.age KEY=path/to/job-tracker-backup.key
```

It decrypts the file and restores it into a separate local database, `jobtracker_restore`
(recreated each time, never the one `make dev` uses), to inspect with
`docker compose exec postgres psql -U <user> -d jobtracker_restore`. To recover
production, restore the same way into a fresh database and point `DATABASE_URL` at it
(the dump holds no roles or grants, so run `pg_restore --no-owner` as your app role).

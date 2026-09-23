#!/bin/sh
# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Runs once, when the local Postgres volume is first initialised. Creates the role the
# app connects as and makes it the database owner. It is deliberately NOT a superuser and
# has NO BYPASSRLS: either would silently skip row-level security. CREATEDB is local-only,
# so the test suite can create its own `<db>_test` database (production's role lacks it).
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v app_user="$APP_DB_USER" -v app_password="$APP_DB_PASSWORD" -v db="$POSTGRES_DB" <<'SQL'
CREATE ROLE :"app_user" LOGIN PASSWORD :'app_password'
  NOSUPERUSER NOBYPASSRLS NOCREATEROLE CREATEDB;
ALTER DATABASE :"db" OWNER TO :"app_user";
SQL

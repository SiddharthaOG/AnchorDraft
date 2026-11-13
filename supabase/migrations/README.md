# Supabase database setup

This directory contains the ordered SQL migrations for the AnchorDraft PostgreSQL schema. Migrations are the source-controlled record of schema changes. Local demo seed scripts are kept separately under `supabase/seed/`.

## Prerequisites

- Supabase CLI installed.
- Docker Desktop or another Docker-compatible runtime running.
- From the repository root, not from inside `supabase/`.

## Fresh local setup

```bash
# From the repository root
supabase start
supabase status

# Rebuild the local database from the checked-in migration chain.
# This is destructive to the LOCAL Supabase database only.
supabase db reset
```

The local stack normally exposes:
- API: `http://127.0.0.1:54321`
- Studio: `http://127.0.0.1:54323`
- PostgreSQL: `127.0.0.1:55432`

Use the actual values printed by `supabase status`. The repository's `supabase/config.toml` currently has automatic seed execution disabled, so `db reset` applies migrations but does not automatically execute the separate demo seed scripts.

## Local demo data (optional)

The seed scripts require actual Auth user UUIDs. They are not migrations and must not be treated as production account provisioning.

1. Start the local stack and apply migrations using the commands above.
2. Open local Supabase Studio at `http://127.0.0.1:54323`.
3. Create four local Auth users for the sample seed scenario:
   - owner/manager account
   - creator 1
   - creator 2
   - reviewer
4. Obtain their UUIDs from the local Auth users table (or SQL editor).
5. Run `supabase/seed/seed_users.sql` with `owner_uid`, `creator1_uid`, `creator2_uid`, and `reviewer_uid`.
6. Run `supabase/seed/seed_content.sql` with `creator1_uid`.

Example from a shell with `psql` installed and the local database reachable:

```bash
psql "postgresql://postgres:postgres@127.0.0.1:55432/postgres" \
  -v owner_uid='<OWNER_UUID>' \
  -v creator1_uid='<CREATOR1_UUID>' \
  -v creator2_uid='<CREATOR2_UUID>' \
  -v reviewer_uid='<REVIEWER_UUID>' \
  -f supabase/seed/seed_users.sql

psql "postgresql://postgres:postgres@127.0.0.1:55432/postgres" \
  -v creator1_uid='<CREATOR1_UUID>' \
  -f supabase/seed/seed_content.sql
```

The sample seed scenario is a local fixture. It does not define or create the hosted hackathon demo accounts, and its owner/manager role arrangement may differ from the hosted demo-account setup.

## Migration workflow

Create and test migrations locally:

```bash
supabase migration new <short_description>
# Edit the generated SQL file.
supabase db reset
```

Review the SQL and test the full migration chain before committing it. Do not edit an already-applied migration to change a shared database; add a new forward-only migration instead.

For a hosted development/staging project:

```bash
supabase login
supabase link --project-ref <project-ref>
supabase migration list --remote
supabase db push --dry-run --remote
supabase db push --remote
```

Review the migration list and dry-run output before applying. Only one coordinated operator should push migrations to a shared project at a time.

**Production safety:** never run `supabase db reset --remote` against production or the shared AnchorDraft database. Remote reset is destructive. Do not use `--include-seed` on production. Use forward-only migrations and inspect the remote migration history before applying changes.

## Test notes

Schema and RLS integration tests live under `supabase/tests/`. Review the test scripts for their required local Auth users and organisation fixtures before running them. They require a local database and test memberships; they are not covered by simply running the frontend or backend unit-test commands.

## Migration naming

Migration files use timestamp prefixes:

```text
YYYYMMDDHHMMSS_description.sql
```

Keep existing migration filenames stable. Add new schema changes as new timestamped files.

## Shared database note

The staging and production Render services have historically used the same hosted Supabase project. Treat schema and data changes as shared-environment operations. Test with local Supabase first, inspect the migration history, and avoid destructive commands.

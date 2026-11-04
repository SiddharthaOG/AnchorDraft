# Supabase Migrations

This directory contains SQL migration files for the AnchorDraft database schema.

Migrations are applied in order using the Supabase CLI:
```bash
supabase db reset
```

Or for production:
```bash
supabase migration up
```

## Migration Naming Convention

Files are named with a timestamp prefix:
```
YYYYMMDDHHMMSS_description.sql
```

## Current Status

No migrations yet. Migrations will be added in Slice 1 (Schema, Auth, Roles, RLS).
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

## Phase 2 Migrations (Complete)

| # | File | Description |
|---|------|-------------|
| 1 | `20261104000001_enums_and_orgs.sql` | Enumerated types and core identity tables (organizations, profiles, memberships) |
| 2 | `20261104000002_brand_kits.sql` | Brand kits, rules, and approved facts tables |
| 3 | `20261104000003_contents_revisions.sql` | Contents and revisions (append-only) |
| 4 | `20261104000004_reviews_findings.sql` | Reviews and findings (review service only) |
| 5 | `20261104000005_workflow_tables.sql` | Decisions, comments, approvals, audit_log |
| 6 | `20261104000006_views.sql` | Derived views (v_latest_revision, v_finding_state, v_pending_signoffs, v_rule_stats) |
| 7 | `20261104000007_triggers.sql` | BEFORE INSERT triggers to copy org_id from parent tables |
| 8 | `20261104000008_rls_policies.sql` | Row Level Security policies for all application tables |
| 9 | `20261104000009_workflow_functions.sql` | SECURITY DEFINER workflow RPC functions (10 user-facing + 2 service-only) |
| 10 | `20261104000010_seed_data.sql` | Core seed data: fictional organization only (NO auth.users references) |

## Seed Data (Separate Executable Scripts)

The seed data is split to avoid foreign key violations on `auth.users`. The migration seeds only the organization. Demo users must be created in Supabase Auth first, then seed scripts are executed with their actual UUIDs.

| Script | Description | When to Run |
|--------|-------------|-------------|
| `20261104000010_seed_data.sql` | Organization only | Runs with migrations (`supabase db reset`) |
| `supabase/seed/seed_users.sql` | Profiles, memberships, brand kit v1, 15 rules, 5 facts | After creating 4 demo users in Supabase Auth |
| `supabase/seed/seed_content.sql` | Sample content & 2 revisions (planted issues) | After seed_users.sql |

### Seed Data Contents
- 1 organization: "Axial Technologies"
- 4 demo users (owner+manager, 2 creators, 1 reviewer) - created via Supabase Auth
- 1 active brand kit v1 with 15 rules and 5 approved facts
- 1 sample content with 2 revisions (demo scenario with 4 planted issues)

### Seed Setup Procedure (Exact Execution Order)

```bash
# 1. Start local Supabase stack (requires Docker Desktop running)
supabase start

# 2. Reset database and apply all 10 migrations (includes org seed)
supabase db reset

# 3. Create 4 demo users in Supabase Auth (via Studio at http://localhost:54323 or admin API)
#    Emails: owner-mgr@axial.demo, creator1@axial.demo, creator2@axial.demo, reviewer@axial.demo
#    Password: any (e.g., "demo123456")

# 4. Get actual user UUIDs from auth.users
#    In Studio SQL editor or psql:
#    SELECT id, email FROM auth.users WHERE email LIKE '%@axial.demo';

# 5. Execute seed_users.sql with the four actual UUIDs as psql variables
psql -h localhost -p 55432 -U postgres -d postgres \
  -v owner_uid='<OWNER_UUID>' \
  -v creator1_uid='<CREATOR1_UUID>' \
  -v creator2_uid='<CREATOR2_UUID>' \
  -v reviewer_uid='<REVIEWER_UUID>' \
  -f supabase/seed/seed_users.sql

# 6. Execute seed_content.sql with creator1's UUID
psql -h localhost -p 55432 -U postgres -d postgres \
  -v creator1_uid='<CREATOR1_UUID>' \
  -f supabase/seed/seed_content.sql

# 7. Verify seeded data
psql -h localhost -p 55432 -U postgres -d postgres -c "
  SELECT 'organizations' AS table_name, count(*) FROM organizations
  UNION ALL SELECT 'profiles', count(*) FROM profiles
  UNION ALL SELECT 'memberships', count(*) FROM memberships
  UNION ALL SELECT 'brand_kits', count(*) FROM brand_kits
  UNION ALL SELECT 'rules', count(*) FROM rules
  UNION ALL SELECT 'approved_facts', count(*) FROM approved_facts
  UNION ALL SELECT 'contents', count(*) FROM contents
  UNION ALL SELECT 'revisions', count(*) FROM revisions;"
```

**Expected row counts after successful seeding:**
| Table | Expected Count |
|-------|----------------|
| organizations | 1 |
| profiles | 4 |
| memberships | 4 |
| brand_kits | 1 |
| rules | 15 |
| approved_facts | 5 |
| contents | 1 |
| revisions | 2 |

## Local Development Setup

### Prerequisites
- Supabase CLI installed (`npm install -g supabase` or via package manager)
- Docker Desktop installed and running (for local Supabase stack)

### Start Local Supabase
```bash
# From repository root
supabase start
```

This starts:
- PostgreSQL on `localhost:55432`
- Supabase API on `localhost:54321`
- Studio on `localhost:54323`

### Apply Migrations
```bash
# Reset database and apply all migrations
supabase db reset

# Or apply specific migration
supabase migration up
```

### Run Tests
```bash
# Run schema tests (requires local DB)
psql -h localhost -p 55432 -U postgres -d postgres -f supabase/tests/01_schema_integrity.sql

# Run all test suites (requires test user setup in two orgs)
./supabase/tests/run_tests.sh local
```

### Environment Variables
Create `.env.local` for web/engine:
```bash
# Web app
VITE_SUPABASE_URL=http://localhost:54321
VITE_SUPABASE_ANON_KEY=<from supabase start output>
VITE_ENGINE_URL=http://localhost:8000

# Engine
SUPABASE_URL=http://localhost:54321
SUPABASE_SERVICE_ROLE_KEY=<from supabase start output>
LLM_PROVIDER=fake
DAILY_REVIEW_CAP=20
```

## Test Database

For CI/testing, use the test runner:
```bash
./supabase/tests/run_tests.sh local
```

Note: RLS and workflow tests require test users with memberships in different organizations. These are integration tests that should be run against a local Supabase instance with test users created.

## Security Notes

- All workflow state changes go through `SECURITY DEFINER` functions
- Direct INSERT/UPDATE/DELETE on workflow tables revoked from `authenticated` and `anon`
- RLS enabled on all 14 application tables
- Organization isolation enforced via `private.is_member()` and `private.has_role()` helpers
- **RLS helpers granted to `authenticated` in migration 0008** (schema usage + execute on `is_member`/`has_role`)
- Service-only functions (`engine_complete_review`, `engine_fail_review`) have `EXECUTE` granted to `service_role` in the migration (no manual dashboard configuration required)

## Verification Checklist

After running migrations and seed scripts, verify:
- [ ] All 12 enums created
- [ ] All 14 tables created with correct columns, constraints, indexes
- [ ] 4 views created with `security_invoker = true`
- [ ] 4 BEFORE INSERT triggers active
- [ ] RLS enabled on all tables with appropriate policies
- [ ] 10 user-facing workflow functions + 2 service-only functions created
- [ ] Function execute permissions: granted to `authenticated`, revoked from `public`/`anon`
- [ ] Service-only functions: granted to `service_role` in migration
- [ ] Core seed data (organization) inserts without conflicts
- [ ] Seed scripts execute successfully with actual Auth user UUIDs
- [ ] Row counts match expected values (see table above)
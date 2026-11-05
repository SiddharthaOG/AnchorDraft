-- Migration: 20261104000010_seed_data.sql
-- Description: Core seed data - only the fictional organization
-- Brand kit, rules, and approved facts are seeded by supabase/seed/seed_users.sql
-- after demo users exist in auth.users.

-- ============================================================
-- 1. Fictional Organization
-- ============================================================
insert into public.organizations (id, name, created_at)
values (
    '11111111-1111-1111-1111-111111111111',
    'Axial Technologies',
    '2026-11-01 10:00:00+00'
)
on conflict (id) do nothing;
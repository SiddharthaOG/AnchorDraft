-- Migration: 20261104000008_rls_policies.sql
-- Description: Enable RLS and create policies for all application tables

-- Helper functions in private schema (not exposed via PostgREST)
create schema if not exists private;

-- Check if user is a member of the organization
create or replace function private.is_member(_org uuid)
returns boolean language sql stable security definer set search_path = ''
as $$
    select exists (
        select 1 from public.memberships m
        where m.org_id = _org and m.user_id = (select auth.uid())
    )
$$;

-- Check if user has a specific role in the organization
create or replace function private.has_role(_org uuid, _role public.app_role)
returns boolean language sql stable security definer set search_path = ''
as $$
    select exists (
        select 1 from public.memberships m
        where m.org_id = _org and m.user_id = (select auth.uid()) and _role = any (m.roles)
    )
$$;

-- Allow authenticated users to invoke RLS helper functions
grant usage on schema private to authenticated;
grant execute on function private.is_member(uuid) to authenticated;
grant execute on function private.has_role(uuid, public.app_role) to authenticated;

-- ============================================================
-- RLS Policies
-- ============================================================

-- organizations: members can read
alter table public.organizations enable row level security;

create policy organizations_select on public.organizations
    for select to authenticated
    using (private.is_member(id));

-- profiles: members of shared org can read; self can read/write
alter table public.profiles enable row level security;

create policy profiles_select on public.profiles
    for select to authenticated
    using (
        user_id = (select auth.uid())
        or exists (
            select 1 from public.memberships m1
            join public.memberships m2 on m1.org_id = m2.org_id
            where m1.user_id = (select auth.uid())
            and m2.user_id = profiles.user_id
        )
    );

create policy profiles_insert on public.profiles
    for insert to authenticated
    with check (user_id = (select auth.uid()));

create policy profiles_update on public.profiles
    for update to authenticated
    using (user_id = (select auth.uid()))
    with check (user_id = (select auth.uid()));

-- memberships: members can read
alter table public.memberships enable row level security;

create policy memberships_select on public.memberships
    for select to authenticated
    using (private.is_member(org_id));

-- brand_kits: members can read; owner can write (draft only via functions)
alter table public.brand_kits enable row level security;

create policy brand_kits_select on public.brand_kits
    for select to authenticated
    using (private.is_member(org_id));

-- rules: members can read; owner can write only on draft kits
alter table public.rules enable row level security;

create policy rules_select on public.rules
    for select to authenticated
    using (private.is_member(org_id));

create policy rules_write on public.rules
    for all to authenticated
    using (
        private.has_role(org_id, 'owner')
        and exists (
            select 1 from public.brand_kits k
            where k.id = rules.kit_id and k.status = 'draft'
        )
    )
    with check (
        private.has_role(org_id, 'owner')
        and exists (
            select 1 from public.brand_kits k
            where k.id = rules.kit_id and k.status = 'draft'
        )
    );

-- approved_facts: members can read; owner can write only on draft kits
alter table public.approved_facts enable row level security;

create policy approved_facts_select on public.approved_facts
    for select to authenticated
    using (private.is_member(org_id));

create policy approved_facts_write on public.approved_facts
    for all to authenticated
    using (
        private.has_role(org_id, 'owner')
        and exists (
            select 1 from public.brand_kits k
            where k.id = approved_facts.kit_id and k.status = 'draft'
        )
    )
    with check (
        private.has_role(org_id, 'owner')
        and exists (
            select 1 from public.brand_kits k
            where k.id = approved_facts.kit_id and k.status = 'draft'
        )
    );

-- contents: members can read; creators/managers/owners can create via functions
alter table public.contents enable row level security;

create policy contents_select on public.contents
    for select to authenticated
    using (private.is_member(org_id));

-- revisions: members can read; workflow functions write
alter table public.revisions enable row level security;

create policy revisions_select on public.revisions
    for select to authenticated
    using (private.is_member(org_id));

-- reviews: members can read; review service writes
alter table public.reviews enable row level security;

create policy reviews_select on public.reviews
    for select to authenticated
    using (private.is_member(org_id));

-- findings: members can read; review service writes
alter table public.findings enable row level security;

create policy findings_select on public.findings
    for select to authenticated
    using (private.is_member(org_id));

-- decisions: members can read; workflow functions write
alter table public.decisions enable row level security;

create policy decisions_select on public.decisions
    for select to authenticated
    using (private.is_member(org_id));

-- comments: members can read; any member can insert as themselves
alter table public.comments enable row level security;

create policy comments_select on public.comments
    for select to authenticated
    using (private.is_member(org_id));

create policy comments_insert on public.comments
    for insert to authenticated
    with check (
        user_id = (select auth.uid())
        and private.is_member(org_id)
    );

-- approvals: members can read; workflow functions write
alter table public.approvals enable row level security;

create policy approvals_select on public.approvals
    for select to authenticated
    using (private.is_member(org_id));

-- audit_log: managers and owners can read
alter table public.audit_log enable row level security;

create policy audit_log_select on public.audit_log
    for select to authenticated
    using (
        private.has_role(org_id, 'manager')
        or private.has_role(org_id, 'owner')
    );

-- ============================================================
-- Revoke direct write privileges on workflow tables from authenticated/anon
-- Only SECURITY DEFINER functions can write to these tables
-- ============================================================

revoke insert, update, delete on public.contents from authenticated, anon;
revoke insert, update, delete on public.revisions from authenticated, anon;
revoke insert, update, delete on public.reviews from authenticated, anon;
revoke insert, update, delete on public.findings from authenticated, anon;
revoke insert, update, delete on public.decisions from authenticated, anon;
revoke insert, update, delete on public.approvals from authenticated, anon;
revoke insert, update, delete on public.audit_log from authenticated, anon;

-- Grant select on all tables to authenticated (policies will filter)
grant select on all tables in schema public to authenticated;
-- Migration: 20261104000001_enums_and_orgs.sql
-- Description: Create enumerated types and core identity tables (organizations, profiles, memberships)

-- Private schema for internal helper and trigger functions
create schema if not exists private;

revoke all on schema private from public, anon, authenticated;
-- Enable required extensions
create extension if not exists "pgcrypto"; -- for gen_random_uuid()

-- 1. Enumerated types
create type public.app_role as enum ('creator', 'manager', 'reviewer', 'owner');
create type public.kit_status as enum ('draft', 'active', 'archived');
create type public.rule_category as enum ('tone', 'terminology', 'messaging', 'claim', 'fact', 'accessibility');
create type public.severity as enum ('low', 'medium', 'high');
create type public.check_kind as enum ('deterministic', 'llm');
create type public.content_status as enum ('draft', 'submitted', 'changes_requested', 'approved');
create type public.revision_source as enum ('manual', 'accepted_suggestion', 'import');
create type public.review_status as enum ('queued', 'running', 'done', 'failed');
create type public.finding_source as enum ('deterministic', 'llm');
create type public.llm_status as enum ('ok', 'skipped', 'failed');
create type public.decision_action as enum ('accept', 'edit', 'dismiss');
create type public.approval_action as enum ('approve', 'request_changes', 'signoff', 'reject_claim');

-- 2. Organizations
create table public.organizations (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    created_at timestamptz not null default now()
);

-- 3. Profiles (linked to auth.users)
create table public.profiles (
    user_id uuid primary key references auth.users(id) on delete cascade,
    display_name text not null,
    created_at timestamptz not null default now()
);

-- 4. Memberships (org_id, user_id) as composite primary key
create table public.memberships (
    org_id uuid not null references public.organizations(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    roles public.app_role[] not null default '{creator}'::public.app_role[]
        check (cardinality(roles) > 0),
    created_at timestamptz not null default now(),
    primary key (org_id, user_id)
);

-- Index for looking up memberships by user_id
create index idx_memberships_user_id on public.memberships (user_id);
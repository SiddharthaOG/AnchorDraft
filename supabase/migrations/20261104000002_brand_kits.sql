-- Migration: 20261104000002_brand_kits.sql
-- Description: Create brand kits, rules, and approved facts tables

-- 1. Brand kits
create table public.brand_kits (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations(id) on delete cascade,
    version int not null,
    name text not null,
    status public.kit_status not null default 'draft',
    source_kit_id uuid null references public.brand_kits(id) on delete set null,
    created_by uuid not null references auth.users(id) on delete restrict,
    created_at timestamptz not null default now(),
    activated_at timestamptz null,
    constraint brand_kits_unique_org_version unique (org_id, version)
);

-- Partial unique index: one active kit per org
create unique index idx_brand_kits_one_active_per_org
    on public.brand_kits (org_id)
    where status = 'active';

-- Index for listing kits by org and status
create index idx_brand_kits_org_status on public.brand_kits (org_id, status);

-- 2. Rules
create table public.rules (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null, -- copied from kit by trigger
    kit_id uuid not null references public.brand_kits(id) on delete cascade,
    rule_key text not null check (rule_key ~ '^[A-Z0-9]+-[0-9]{2,3}$'),
    category public.rule_category not null,
    title text not null,
    guideline_text text not null,
    severity public.severity not null default 'medium',
    check_kind public.check_kind not null,
    config jsonb null,
    needs_reviewer boolean not null default false,
    example_bad text null,
    example_good text null,
    constraint rules_unique_kit_rule_key unique (kit_id, rule_key)
);

-- Index for rules by kit_id
create index idx_rules_kit_id on public.rules (kit_id);

-- Index for rules by org_id and ref_key (for stats)
create index idx_rules_org_ref_key on public.rules (org_id, rule_key);

-- 3. Approved facts
create table public.approved_facts (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null, -- copied from kit by trigger
    kit_id uuid not null references public.brand_kits(id) on delete cascade,
    fact_key text not null check (fact_key ~ '^[A-Z0-9]+-[0-9]{2,3}$'),
    statement text not null,
    source_note text not null,
    valid_until date null,
    constraint approved_facts_unique_kit_fact_key unique (kit_id, fact_key)
);

-- Index for approved_facts by kit_id
create index idx_approved_facts_kit_id on public.approved_facts (kit_id);

-- Index for approved_facts by org_id and ref_key (for stats)
create index idx_approved_facts_org_ref_key on public.approved_facts (org_id, fact_key);
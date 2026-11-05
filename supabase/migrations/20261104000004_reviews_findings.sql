-- Migration: 20261104000004_reviews_findings.sql
-- Description: Create reviews and findings tables

-- 1. Reviews (written only by review service via service role)
create table public.reviews (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations(id) on delete cascade,
    revision_id uuid not null references public.revisions(id) on delete cascade,
    kit_id uuid not null references public.brand_kits(id) on delete cascade,
    status public.review_status not null default 'queued',
    error text null,
    engine_version text not null,
    model text null,
    prompt_version text null,
    llm_status public.llm_status not null default 'ok',
    warnings jsonb not null default '[]',
    llm_findings_raw int not null default 0,
    llm_findings_dropped int not null default 0,
    validator_stats jsonb not null default '{}',
    requested_by uuid not null references auth.users(id) on delete restrict,
    created_at timestamptz not null default now(),
    started_at timestamptz null,
    finished_at timestamptz null
);

-- Index for reviews by revision_id and created_at desc
create index idx_reviews_revision_created on public.reviews (revision_id, created_at desc);

-- Index for reviews by org_id and status
create index idx_reviews_org_status on public.reviews (org_id, status);

-- 2. Findings (written only by review service via service role)
create table public.findings (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null, -- copied from review by trigger
    review_id uuid not null references public.reviews(id) on delete cascade,
    source public.finding_source not null,
    rule_id uuid null references public.rules(id) on delete set null,
    fact_id uuid null references public.approved_facts(id) on delete set null,
    ref_key text not null,
    category public.rule_category not null,
    severity public.severity not null,
    quote text not null,
    start_offset int not null,
    end_offset int not null,
    explanation text not null,
    suggestion text null,
    confidence numeric(3,2) null check (confidence is null or (confidence >= 0 and confidence <= 1)),
    needs_human boolean not null default false,
    needs_reviewer boolean not null default false,
    created_at timestamptz not null default now(),
    constraint findings_one_ref check (num_nonnulls(rule_id, fact_id) = 1),
    constraint findings_offsets_valid check (start_offset >= 0 and end_offset > start_offset)
);

-- Index for findings by review_id
create index idx_findings_review_id on public.findings (review_id);

-- Index for findings by org_id and ref_key (for stats)
create index idx_findings_org_ref_key on public.findings (org_id, ref_key);
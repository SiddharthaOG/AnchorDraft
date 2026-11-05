-- Migration: 20261104000003_contents_revisions.sql
-- Description: Create contents and revisions tables

-- 1. Contents
create table public.contents (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations(id) on delete cascade,
    title text not null check (length(title) between 1 and 200),
    channel text not null default 'other'
        check (channel in ('linkedin','blog','email','website','other')),
    purpose text not null check (length(purpose) between 1 and 1000),
    status public.content_status not null default 'draft',
    created_by uuid not null references auth.users(id) on delete restrict,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- Index for contents by org, status, and creation time
create index idx_contents_org_status_created on public.contents (org_id, status, created_at desc);

-- 2. Revisions (append-only, inserted only by database functions)
create table public.revisions (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null, -- copied from content by trigger
    content_id uuid not null references public.contents(id) on delete cascade,
    version int not null,
    parent_revision_id uuid null references public.revisions(id) on delete set null,
    body text not null check (length(body) between 1 and 20000),
    source public.revision_source not null,
    created_by uuid not null references auth.users(id) on delete restrict,
    created_at timestamptz not null default now(),
    constraint revisions_unique_content_version unique (content_id, version)
);

-- Index for revisions by content_id and version (descending for latest)
create index idx_revisions_content_version on public.revisions (content_id, version desc);

-- Index for revisions by org_id
create index idx_revisions_org_id on public.revisions (org_id);
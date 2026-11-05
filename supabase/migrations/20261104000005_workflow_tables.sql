-- Migration: 20261104000005_workflow_tables.sql
-- Description: Create decisions, comments, approvals, and audit_log tables

-- 1. Decisions (append-only, written only by record_decision and apply_decisions)
create table public.decisions (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations(id) on delete cascade,
    finding_id uuid not null references public.findings(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete restrict,
    action public.decision_action not null,
    reason text null,
    edited_text text null,
    resulting_revision_id uuid null references public.revisions(id) on delete set null,
    created_at timestamptz not null default now(),
    constraint decisions_dismiss_requires_reason check (
        action <> 'dismiss' or (reason is not null and length(btrim(reason)) > 0)
    ),
    constraint decisions_edit_requires_text check (
        action <> 'edit' or (edited_text is not null and length(edited_text) > 0)
    )
);

-- Index for decisions by finding_id and created_at desc (latest decision first)
create index idx_decisions_finding_created on public.decisions (finding_id, created_at desc);

-- 2. Comments (append-only)
create table public.comments (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations(id) on delete cascade,
    content_id uuid not null references public.contents(id) on delete cascade,
    revision_id uuid null references public.revisions(id) on delete set null,
    finding_id uuid null references public.findings(id) on delete set null,
    user_id uuid not null references auth.users(id) on delete restrict,
    body text not null check (length(body) between 1 and 2000),
    created_at timestamptz not null default now()
);

-- Index for comments by content_id and created_at
create index idx_comments_content_created on public.comments (content_id, created_at);

-- 3. Approvals (append-only, written only by workflow functions)
create table public.approvals (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations(id) on delete cascade,
    content_id uuid not null references public.contents(id) on delete cascade,
    revision_id uuid not null references public.revisions(id) on delete cascade,
    finding_id uuid null references public.findings(id) on delete set null,
    user_id uuid not null references auth.users(id) on delete restrict,
    action public.approval_action not null,
    note text null,
    created_at timestamptz not null default now(),
    constraint approvals_signoff_requires_finding check (
        action not in ('signoff', 'reject_claim') or finding_id is not null
    ),
    constraint approvals_approve_no_finding check (
        action not in ('approve', 'request_changes') or finding_id is null
    ),
    constraint approvals_request_changes_requires_note check (
        action <> 'request_changes' or (note is not null and length(btrim(note)) > 0)
    ),
    constraint approvals_reject_claim_requires_note check (
        action <> 'reject_claim' or (note is not null and length(btrim(note)) > 0)
    )
);

-- Index for approvals by content_id and created_at desc
create index idx_approvals_content_created on public.approvals (content_id, created_at desc);

-- Index for approvals by finding_id
create index idx_approvals_finding_id on public.approvals (finding_id);

-- 4. Audit log (append-only, written by workflow functions and review service)
create table public.audit_log (
    id bigint generated always as identity primary key,
    org_id uuid not null references public.organizations(id) on delete cascade,
    actor_id uuid null references auth.users(id) on delete set null,
    action text not null,
    entity_type text not null,
    entity_id uuid not null,
    detail jsonb null,
    created_at timestamptz not null default now()
);

-- Index for audit_log by org_id and created_at desc
create index idx_audit_log_org_created on public.audit_log (org_id, created_at desc);
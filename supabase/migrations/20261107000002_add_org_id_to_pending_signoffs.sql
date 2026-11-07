-- Migration: 20261107000002_add_org_id_to_pending_signoffs.sql
-- Description: Add org_id column to v_pending_signoffs view for org-scoped queries

-- v_pending_signoffs: findings with needs_reviewer = true in the latest done review
-- of a content's latest revision that have no signoff approval
create or replace view public.v_pending_signoffs with (security_invoker = true) as
select
    c.id as content_id,
    f.id as finding_id,
    f.ref_key,
    f.category,
    f.severity,
    f.quote,
    f.explanation,
    f.needs_human,
    c.org_id as org_id
from public.contents c
inner join public.v_latest_revision lr on lr.content_id = c.id
inner join public.reviews r on r.revision_id = lr.revision_id
    and r.status = 'done'
    and r.llm_status in ('ok', 'skipped')
inner join public.findings f on f.review_id = r.id
    and f.needs_reviewer = true
where c.status = 'submitted'
    and not exists (
        select 1
        from public.approvals a
        where a.finding_id = f.id
            and a.action = 'signoff'
    );
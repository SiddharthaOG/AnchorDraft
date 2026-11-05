-- Migration: 20261104000006_views.sql
-- Description: Create derived views for common queries

-- v_latest_revision: for each content, its highest-version revision
create view public.v_latest_revision with (security_invoker = true) as
select
    r.content_id,
    r.id as revision_id,
    r.version,
    r.body,
    r.source,
    r.created_by,
    r.created_at
from public.revisions r
inner join (
    select content_id, max(version) as max_version
    from public.revisions
    group by content_id
) latest on latest.content_id = r.content_id and latest.max_version = r.version;

-- v_finding_state: each finding joined to its latest decision
create view public.v_finding_state with (security_invoker = true) as
select
    f.*,
    d.action as last_action,
    d.reason as last_reason,
    d.edited_text as last_edited_text,
    d.resulting_revision_id,
    d.created_at as decided_at
from public.findings f
left join lateral (
    select *
    from public.decisions d
    where d.finding_id = f.id
    order by d.created_at desc
    limit 1
) d on true;

-- v_pending_signoffs: findings with needs_reviewer = true in the latest done review
-- of a content's latest revision that have no signoff approval
create view public.v_pending_signoffs with (security_invoker = true) as
select
    c.id as content_id,
    f.id as finding_id,
    f.ref_key,
    f.category,
    f.severity,
    f.quote,
    f.explanation,
    f.needs_human
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

-- v_rule_stats: per organisation and ref_key stats
create view public.v_rule_stats with (security_invoker = true) as
select
    s.org_id,
    s.ref_key,
    s.category,
    count(*) as findings,
    count(*) filter (where s.last_action = 'dismiss') as dismissed,
    count(*) filter (where s.last_action in ('accept','edit')) as acted_on,
    round(
        count(*) filter (where s.last_action = 'dismiss')::numeric
        / nullif(count(*) filter (where s.last_action is not null), 0), 2
    ) as dismissal_rate,
    max(s.created_at) as last_seen
from public.v_finding_state s
group by s.org_id, s.ref_key, s.category;
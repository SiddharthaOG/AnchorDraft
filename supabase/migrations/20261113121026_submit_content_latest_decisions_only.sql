-- Only the latest decision per finding can block submission.
create or replace function public.submit_content(
    _content_id uuid
)
returns void
language plpgsql security definer set search_path = ''
as $$
declare
    _uid uuid := (select auth.uid());
    _org uuid;
    _status public.content_status;
    _latest_revision_id uuid;
    _latest_review_id uuid;
    _review_llm_status public.llm_status;
    _undecided_count int;
    _pending_apply_count int;
begin
    -- 1. Authenticate
    if _uid is null then
        raise exception 'unauthenticated';
    end if;

    -- 2. Lock content and read state
    select org_id, status into _org, _status
    from public.contents
    where id = _content_id
    for update;

    if not found then
        raise exception 'not_found';
    end if;

    -- 3. Validate membership and role
    if not private.has_role(_org, 'creator') then
        raise exception 'forbidden';
    end if;

    -- 4. Check current status is draft
    if _status <> 'draft' then
        raise exception 'conflict:not_editable';
    end if;

    -- 5. Get latest revision
    select id into _latest_revision_id
    from public.revisions
    where content_id = _content_id
    order by version desc
    limit 1;

    if _latest_revision_id is null then
        raise exception 'conflict:no_revision';
    end if;

    -- 6. Get latest done review with ok/skipped llm_status
    select r.id, r.llm_status into _latest_review_id, _review_llm_status
    from public.reviews r
    where r.revision_id = _latest_revision_id
      and r.status = 'done'
      and r.llm_status in ('ok', 'skipped')
    order by r.created_at desc
    limit 1;

    if _latest_review_id is null then
        raise exception 'conflict:no_review';
    end if;

    if _review_llm_status = 'failed' then
        raise exception 'conflict:llm_failed';
    end if;

    -- 7. Check all findings have decisions
    select count(*) into _undecided_count
    from public.findings f
    left join lateral (
        select 1 from public.decisions d
        where d.finding_id = f.id
        order by d.created_at desc, d.id desc
        limit 1
    ) d on true
    where f.review_id = _latest_review_id
      and d is null;

    if _undecided_count > 0 then
        raise exception 'conflict:findings_undecided';
    end if;

    -- 8. Check no accepted/edited decisions waiting to be applied
    select count(*) into _pending_apply_count
    from public.decisions d
    join public.findings f on f.id = d.finding_id
    where f.review_id = _latest_review_id
      and d.action in ('accept', 'edit')
      and d.resulting_revision_id is null
      and not exists (
          select 1
          from public.decisions newer
          where newer.finding_id = d.finding_id
            and (newer.created_at, newer.id) > (d.created_at, d.id)
      );

    if _pending_apply_count > 0 then
        raise exception 'conflict:changes_pending_apply';
    end if;

    -- 9. Update status to submitted
    update public.contents
    set status = 'submitted', updated_at = now()
    where id = _content_id;

    -- 10. Audit log
    insert into public.audit_log (org_id, actor_id, action, entity_type, entity_id)
    values (_org, _uid, 'content.submitted', 'content', _content_id);
end $$;

-- Keep the read model's latest-decision selection deterministic and aligned
-- with submit_content's pending-apply guard.
create or replace view public.v_finding_state with (security_invoker = true) as
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
    order by d.created_at desc, d.id desc
    limit 1
) d on true;

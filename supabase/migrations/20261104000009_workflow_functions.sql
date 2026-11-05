-- Migration: 20261104000009_workflow_functions.sql
-- Description: Create workflow RPC functions with SECURITY DEFINER hardening
-- These functions enforce all state transitions and authorization at the database boundary
-- Helper functions (is_member, has_role) are defined in 20261104000008_rls_policies.sql

-- ============================================================
-- 1. create_content
-- ============================================================
create or replace function public.create_content(
    _org uuid,
    _title text,
    _channel text,
    _purpose text,
    _body text
)
returns table (content_id uuid, revision_id uuid)
language plpgsql security definer set search_path = ''
as $$
declare
    _uid uuid := (select auth.uid());
    _new_content_id uuid;
    _new_revision_id uuid;
begin
    -- 1. Authenticate
    if _uid is null then
        raise exception 'unauthenticated';
    end if;

    -- 2. Validate membership and role
    if not private.has_role(_org, 'creator') then
        raise exception 'forbidden';
    end if;

    -- 3. Validate inputs
    if length(_title) < 1 or length(_title) > 200 then
        raise exception 'validation:title';
    end if;
    if _channel not in ('linkedin','blog','email','website','other') then
        raise exception 'validation:channel';
    end if;
    if length(_purpose) < 1 or length(_purpose) > 1000 then
        raise exception 'validation:purpose';
    end if;
    if length(_body) < 1 or length(_body) > 20000 then
        raise exception 'validation:body';
    end if;

    -- 4. Insert content (draft status)
    insert into public.contents (org_id, title, channel, purpose, status, created_by)
    values (_org, _title, _channel, _purpose, 'draft', _uid)
    returning id into _new_content_id;

    -- 5. Insert revision 1
    insert into public.revisions (content_id, version, body, source, created_by)
    values (_new_content_id, 1, _body, 'manual', _uid)
    returning id into _new_revision_id;

    -- 6. Audit log
    insert into public.audit_log (org_id, actor_id, action, entity_type, entity_id)
    values (_org, _uid, 'content.created', 'content', _new_content_id);

    -- 7. Return
    return query select _new_content_id, _new_revision_id;
end $$;

revoke all on function public.create_content(uuid,text,text,text,text) from public, anon;
grant execute on function public.create_content(uuid,text,text,text,text) to authenticated;

-- ============================================================
-- 2. create_revision
-- ============================================================
create or replace function public.create_revision(
    _content_id uuid,
    _body text
)
returns table (revision_id uuid, version int)
language plpgsql security definer set search_path = ''
as $$
declare
    _uid uuid := (select auth.uid());
    _org uuid;
    _status public.content_status;
    _latest_version int;
    _new_revision_id uuid;
    _new_version int;
    _latest_body text;
begin
    -- 1. Authenticate
    if _uid is null then
        raise exception 'unauthenticated';
    end if;

    -- 2. Lock content row and read state
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

    -- 4. Check content is editable (draft or changes_requested)
    if _status not in ('draft', 'changes_requested') then
        raise exception 'conflict:not_editable';
    end if;

    -- 5. Validate body
    if length(_body) < 1 or length(_body) > 20000 then
        raise exception 'validation:body';
    end if;

    -- 6. Get latest revision body to check for no-op
    select body into _latest_body
    from public.revisions
    where content_id = _content_id
    order by version desc
    limit 1;

    if _latest_body = _body then
        raise exception 'validation:body';
    end if;

    -- 7. Get next version
    select coalesce(max(version), 0) + 1 into _new_version
    from public.revisions
    where content_id = _content_id;

    -- 8. Insert new revision
    insert into public.revisions (content_id, version, parent_revision_id, body, source, created_by)
    select _content_id, _new_version, id, _body, 'manual', _uid
    from public.revisions
    where content_id = _content_id
    order by version desc
    limit 1
    returning id into _new_revision_id;

    -- 9. If status was changes_requested, move to draft
    if _status = 'changes_requested' then
        update public.contents
        set status = 'draft', updated_at = now()
        where id = _content_id;
    end if;

    -- 10. Audit log
    insert into public.audit_log (org_id, actor_id, action, entity_type, entity_id, detail)
    values (_org, _uid, 'revision.created', 'revision', _new_revision_id, jsonb_build_object('version', _new_version));

    -- 11. Return
    return query select _new_revision_id, _new_version;
end $$;

revoke all on function public.create_revision(uuid,text) from public, anon;
grant execute on function public.create_revision(uuid,text) to authenticated;

-- ============================================================
-- 3. record_decision
-- ============================================================
create or replace function public.record_decision(
    _finding_id uuid,
    _action public.decision_action,
    _reason text default null,
    _edited_text text default null
)
returns table (decision_id uuid)
language plpgsql security definer set search_path = ''
as $$
declare
    _uid uuid := (select auth.uid());
    _org uuid;
    _finding_org uuid;
    _review_id uuid;
    _content_id uuid;
    _content_status public.content_status;
    _latest_review_id uuid;
    _latest_revision_id uuid;
    _has_suggestion boolean;
begin
    -- 1. Authenticate
    if _uid is null then
        raise exception 'unauthenticated';
    end if;

    -- 2. Get finding and its review/content
    select f.org_id, f.review_id, r.revision_id, c.id, c.status
    into _finding_org, _review_id, _latest_revision_id, _content_id, _content_status
    from public.findings f
    join public.reviews r on r.id = f.review_id
    join public.revisions rv on rv.id = r.revision_id
    join public.contents c on c.id = rv.content_id
    where f.id = _finding_id;

    if not found then
        raise exception 'not_found';
    end if;

    _org := _finding_org;

    -- 3. Validate membership and role
    if not private.has_role(_org, 'creator') then
        raise exception 'forbidden';
    end if;

    -- 4. Check content is editable
    if _content_status not in ('draft', 'changes_requested') then
        raise exception 'conflict:not_editable';
    end if;

    -- 5. Verify this finding belongs to the latest review of the latest revision
    select r.id into _latest_review_id
    from public.reviews r
    join public.revisions rv on rv.id = r.revision_id
    where rv.content_id = _content_id
      and r.status = 'done'
      and r.llm_status in ('ok', 'skipped')
    order by r.created_at desc
    limit 1;

    if _latest_review_id is null or _latest_review_id <> _review_id then
        raise exception 'conflict:not_latest_review';
    end if;

    -- 6. Validate action-specific requirements
    if _action = 'dismiss' then
        if _reason is null or length(btrim(_reason)) = 0 then
            raise exception 'validation:reason';
        end if;
        if length(_reason) > 1000 then
            raise exception 'validation:reason';
        end if;
    elsif _action = 'edit' then
        if _edited_text is null or length(_edited_text) = 0 then
            raise exception 'validation:edited_text';
        end if;
        if length(_edited_text) > 2000 then
            raise exception 'validation:edited_text';
        end if;
    elsif _action = 'accept' then
        -- Check finding has a suggestion
        select suggestion is not null into _has_suggestion
        from public.findings
        where id = _finding_id;

        if not _has_suggestion then
            raise exception 'conflict:no_suggestion';
        end if;
    end if;

    -- 7. Insert decision
    insert into public.decisions (org_id, finding_id, user_id, action, reason, edited_text)
    values (_org, _finding_id, _uid, _action, _reason, _edited_text)
    returning id into _uid; -- reuse _uid variable for decision_id

    -- 8. Audit log
    insert into public.audit_log (org_id, actor_id, action, entity_type, entity_id, detail)
    values (_org, (select auth.uid()), 'decision.recorded', 'decision', _uid, jsonb_build_object('finding_id', _finding_id, 'action', _action));

    -- 9. Return
    return query select _uid;
end $$;

revoke all on function public.record_decision(uuid,public.decision_action,text,text) from public, anon;
grant execute on function public.record_decision(uuid,public.decision_action,text,text) to authenticated;

-- ============================================================
-- 4. apply_decisions
-- ============================================================
create or replace function public.apply_decisions(
    _content_id uuid
)
returns table (revision_id uuid, version int, applied int, skipped jsonb)
language plpgsql security definer set search_path = ''
as $$
declare
    _uid uuid := (select auth.uid());
    _org uuid;
    _status public.content_status;
    _latest_revision_id uuid;
    _latest_review_id uuid;
    _latest_body text;
    _new_body text;
    _new_version int;
    _new_revision_id uuid;
    _decision_record record;
    _applied_count int := 0;
    _skipped jsonb := '[]'::jsonb;
    _skip_record jsonb;
    _quote_start int;
    _quote_end int;
    _replacement_text text;
    _found boolean;
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

    -- 4. Check content is editable
    if _status not in ('draft', 'changes_requested') then
        raise exception 'conflict:not_editable';
    end if;

    -- 5. Get latest revision and its review
    select r.id, r.revision_id
    into _latest_review_id, _latest_revision_id
    from public.reviews r
    join public.revisions rv on rv.id = r.revision_id
    where rv.content_id = _content_id
      and r.status = 'done'
      and r.llm_status in ('ok', 'skipped')
    order by r.created_at desc
    limit 1;

    if _latest_review_id is null then
        raise exception 'conflict:no_review';
    end if;

    -- 6. Get latest revision body
    select body into _latest_body
    from public.revisions
    where id = _latest_revision_id;

    _new_body := _latest_body;

    -- 7. Collect pending accepted/edited decisions from latest review
    -- Order by start_offset DESC so we apply from end to beginning (offsets stay valid)
    for _decision_record in
        select d.id as decision_id, d.action, d.edited_text, f.quote, f.start_offset, f.end_offset, f.suggestion
        from public.decisions d
        join public.findings f on f.id = d.finding_id
        where f.review_id = _latest_review_id
          and d.action in ('accept', 'edit')
          and d.resulting_revision_id is null
          and d.user_id = _uid
        order by f.start_offset desc
    loop
        -- Verify quote still matches at the current offsets
        _quote_start := _decision_record.start_offset;
        _quote_end := _decision_record.end_offset;

        if _quote_start < 0 or _quote_end > length(_new_body) or _quote_start >= _quote_end then
            _skip_record := jsonb_build_object('finding_id', _decision_record.decision_id, 'reason', 'text_changed');
            _skipped := _skipped || _skip_record;
            continue;
        end if;

        if substring(_new_body from _quote_start + 1 for _quote_end - _quote_start) <> _decision_record.quote then
            _skip_record := jsonb_build_object('finding_id', _decision_record.decision_id, 'reason', 'text_changed');
            _skipped := _skipped || _skip_record;
            continue;
        end if;

        -- Check for overlap with already applied changes (since we go backwards, later changes have higher offsets)
        -- This is implicitly handled by processing in descending offset order

        -- Determine replacement text
        if _decision_record.action = 'accept' then
            _replacement_text := _decision_record.suggestion;
        else -- edit
            _replacement_text := _decision_record.edited_text;
        end if;

        -- Apply replacement
        _new_body := substring(_new_body from 1 for _quote_start) || _replacement_text || substring(_new_body from _quote_end + 1);

        -- Update decision with resulting_revision_id (will be set after insert)
        -- We'll update after creating the revision
        _applied_count := _applied_count + 1;
    end loop;

    -- 8. Check if any changes were applied
    if _applied_count = 0 then
        raise exception 'conflict:no_changes';
    end if;

    -- 9. Validate new body length
    if length(_new_body) > 20000 then
        raise exception 'validation:body';
    end if;

    -- 10. Get next version
    select coalesce(max(version), 0) + 1 into _new_version
    from public.revisions
    where content_id = _content_id;

    -- 11. Insert new revision
    insert into public.revisions (content_id, version, parent_revision_id, body, source, created_by)
    values (_content_id, _new_version, _latest_revision_id, _new_body, 'accepted_suggestion', _uid)
    returning id into _new_revision_id;

    -- 12. Update applied decisions with resulting_revision_id
    update public.decisions d
    set resulting_revision_id = _new_revision_id
    from public.findings f
    where d.finding_id = f.id
      and f.review_id = _latest_review_id
      and d.action in ('accept', 'edit')
      and d.resulting_revision_id is null
      and d.user_id = _uid;

    -- 13. If status was changes_requested, move to draft
    if _status = 'changes_requested' then
        update public.contents
        set status = 'draft', updated_at = now()
        where id = _content_id;
    end if;

    -- 14. Audit log
    insert into public.audit_log (org_id, actor_id, action, entity_type, entity_id, detail)
    values (_org, _uid, 'revision.applied_decisions', 'revision', _new_revision_id, jsonb_build_object('version', _new_version, 'applied', _applied_count, 'skipped', _skipped));

    -- 15. Return
    return query select _new_revision_id, _new_version, _applied_count, _skipped;
end $$;

revoke all on function public.apply_decisions(uuid) from public, anon;
grant execute on function public.apply_decisions(uuid) to authenticated;

-- ============================================================
-- 5. submit_content
-- ============================================================
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
        order by d.created_at desc
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
      and d.resulting_revision_id is null;

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

revoke all on function public.submit_content(uuid) from public, anon;
grant execute on function public.submit_content(uuid) to authenticated;

-- ============================================================
-- 6. request_changes
-- ============================================================
create or replace function public.request_changes(
    _content_id uuid,
    _note text
)
returns void
language plpgsql security definer set search_path = ''
as $$
declare
    _uid uuid := (select auth.uid());
    _org uuid;
    _status public.content_status;
    _latest_revision_id uuid;
begin
    -- 1. Authenticate
    if _uid is null then
        raise exception 'unauthenticated';
    end if;

    -- 2. Validate note
    if _note is null or length(btrim(_note)) = 0 then
        raise exception 'validation:note';
    end if;
    if length(_note) > 2000 then
        raise exception 'validation:note';
    end if;

    -- 3. Lock content and read state
    select org_id, status into _org, _status
    from public.contents
    where id = _content_id
    for update;

    if not found then
        raise exception 'not_found';
    end if;

    -- 4. Validate membership and role
    if not private.has_role(_org, 'manager') then
        raise exception 'forbidden';
    end if;

    -- 5. Check status is submitted
    if _status <> 'submitted' then
        raise exception 'conflict:not_submitted';
    end if;

    -- 6. Get latest revision
    select id into _latest_revision_id
    from public.revisions
    where content_id = _content_id
    order by version desc
    limit 1;

    -- 7. Insert approval row
    insert into public.approvals (org_id, content_id, revision_id, user_id, action, note)
    values (_org, _content_id, _latest_revision_id, _uid, 'request_changes', _note);

    -- 8. Update status
    update public.contents
    set status = 'changes_requested', updated_at = now()
    where id = _content_id;

    -- 9. Audit log
    insert into public.audit_log (org_id, actor_id, action, entity_type, entity_id, detail)
    values (_org, _uid, 'content.changes_requested', 'content', _content_id, jsonb_build_object('note', _note));
end $$;

revoke all on function public.request_changes(uuid,text) from public, anon;
grant execute on function public.request_changes(uuid,text) to authenticated;

-- ============================================================
-- 7. record_signoff
-- ============================================================
create or replace function public.record_signoff(
    _finding_id uuid,
    _action public.approval_action,
    _note text default null
)
returns void
language plpgsql security definer set search_path = ''
as $$
declare
    _uid uuid := (select auth.uid());
    _org uuid;
    _finding_org uuid;
    _review_id uuid;
    _content_id uuid;
    _content_status public.content_status;
    _latest_review_id uuid;
    _latest_revision_id uuid;
    _needs_reviewer boolean;
begin
    -- 1. Authenticate
    if _uid is null then
        raise exception 'unauthenticated';
    end if;

    -- 2. Validate action
    if _action not in ('signoff', 'reject_claim') then
        raise exception 'validation:action';
    end if;

    if _action = 'reject_claim' and (_note is null or length(btrim(_note)) = 0) then
        raise exception 'validation:note';
    end if;
    if _note is not null and length(_note) > 2000 then
        raise exception 'validation:note';
    end if;

    -- 3. Get finding, its review, and content
    select f.org_id, f.review_id, f.needs_reviewer, r.revision_id, c.id, c.status
    into _finding_org, _review_id, _needs_reviewer, _latest_revision_id, _content_id, _content_status
    from public.findings f
    join public.reviews r on r.id = f.review_id
    join public.revisions rv on rv.id = r.revision_id
    join public.contents c on c.id = rv.content_id
    where f.id = _finding_id;

    if not found then
        raise exception 'not_found';
    end if;

    _org := _finding_org;

    -- 4. Validate membership and role
    if not private.has_role(_org, 'reviewer') then
        raise exception 'forbidden';
    end if;

    -- 5. Check content status is submitted
    if _content_status <> 'submitted' then
        raise exception 'conflict:not_submitted';
    end if;

    -- 6. Verify finding needs_reviewer
    if not _needs_reviewer then
        raise exception 'conflict:not_needs_reviewer';
    end if;

    -- 7. Verify this is the latest review of the latest revision
    select r.id, r.revision_id into _latest_review_id, _latest_revision_id
    from public.reviews r
    join public.revisions rv on rv.id = r.revision_id
    where rv.content_id = _content_id
      and r.status = 'done'
      and r.llm_status in ('ok', 'skipped')
    order by r.created_at desc
    limit 1;

    if _latest_review_id is null or _latest_review_id <> _review_id then
        raise exception 'conflict:not_latest_review';
    end if;

    -- 8. Insert approval row
    insert into public.approvals (org_id, content_id, revision_id, finding_id, user_id, action, note)
    values (_org, _content_id, _latest_revision_id, _finding_id, _uid, _action, _note);

    -- 9. If reject_claim, set status to changes_requested
    if _action = 'reject_claim' then
        update public.contents
        set status = 'changes_requested', updated_at = now()
        where id = _content_id;
    end if;

    -- 10. Audit log
    insert into public.audit_log (org_id, actor_id, action, entity_type, entity_id, detail)
    values (_org, _uid, 'approval.recorded', 'approval', _finding_id, jsonb_build_object('action', _action, 'note', _note));
end $$;

revoke all on function public.record_signoff(uuid,public.approval_action,text) from public, anon;
grant execute on function public.record_signoff(uuid,public.approval_action,text) to authenticated;

-- ============================================================
-- 8. approve_content
-- ============================================================
create or replace function public.approve_content(
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
    _pending_signoffs int;
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
    if not private.has_role(_org, 'manager') then
        raise exception 'forbidden';
    end if;

    -- 4. Check status is submitted
    if _status <> 'submitted' then
        raise exception 'conflict:not_submitted';
    end if;

    -- 5. Get latest revision
    select id into _latest_revision_id
    from public.revisions
    where content_id = _content_id
    order by version desc
    limit 1;

    -- 6. Check no pending signoffs (using v_pending_signoffs view)
    select count(*) into _pending_signoffs
    from public.v_pending_signoffs
    where content_id = _content_id;

    if _pending_signoffs > 0 then
        raise exception 'conflict:pending_signoffs';
    end if;

    -- 7. Insert approval row
    insert into public.approvals (org_id, content_id, revision_id, user_id, action)
    values (_org, _content_id, _latest_revision_id, _uid, 'approve');

    -- 8. Update status to approved
    update public.contents
    set status = 'approved', updated_at = now()
    where id = _content_id;

    -- 9. Audit log
    insert into public.audit_log (org_id, actor_id, action, entity_type, entity_id)
    values (_org, _uid, 'content.approved', 'content', _content_id);
end $$;

revoke all on function public.approve_content(uuid) from public, anon;
grant execute on function public.approve_content(uuid) to authenticated;

-- ============================================================
-- 9. clone_kit
-- ============================================================
create or replace function public.clone_kit(
    _kit_id uuid
)
returns table (kit_id uuid, version int)
language plpgsql security definer set search_path = ''
as $$
declare
    _uid uuid := (select auth.uid());
    _org uuid;
    _source_kit public.brand_kits%rowtype;
    _new_version int;
    _new_kit_id uuid;
begin
    -- 1. Authenticate
    if _uid is null then
        raise exception 'unauthenticated';
    end if;

    -- 2. Get source kit
    select * into _source_kit
    from public.brand_kits
    where id = _kit_id;

    if not found then
        raise exception 'not_found';
    end if;

    _org := _source_kit.org_id;

    -- 3. Validate membership and role
    if not private.has_role(_org, 'owner') then
        raise exception 'forbidden';
    end if;

    -- 4. Get next version
    select coalesce(max(version), 0) + 1 into _new_version
    from public.brand_kits
    where org_id = _org;

    -- 5. Create new draft kit
    insert into public.brand_kits (org_id, version, name, status, source_kit_id, created_by)
    values (_org, _new_version, _source_kit.name || ' (copy)', 'draft', _kit_id, _uid)
    returning id into _new_kit_id;

    -- 6. Copy rules
    insert into public.rules (kit_id, rule_key, category, title, guideline_text, severity, check_kind, config, needs_reviewer, example_bad, example_good)
    select _new_kit_id, rule_key, category, title, guideline_text, severity, check_kind, config, needs_reviewer, example_bad, example_good
    from public.rules
    where kit_id = _kit_id;

    -- 7. Copy approved facts
    insert into public.approved_facts (kit_id, fact_key, statement, source_note, valid_until)
    select _new_kit_id, fact_key, statement, source_note, valid_until
    from public.approved_facts
    where kit_id = _kit_id;

    -- 8. Audit log
    insert into public.audit_log (org_id, actor_id, action, entity_type, entity_id, detail)
    values (_org, _uid, 'kit.cloned', 'brand_kit', _new_kit_id, jsonb_build_object('source_kit_id', _kit_id, 'version', _new_version));

    -- 9. Return
    return query select _new_kit_id, _new_version;
end $$;

revoke all on function public.clone_kit(uuid) from public, anon;
grant execute on function public.clone_kit(uuid) to authenticated;

-- ============================================================
-- 10. activate_kit
-- ============================================================
create or replace function public.activate_kit(
    _kit_id uuid
)
returns void
language plpgsql security definer set search_path = ''
as $$
declare
    _uid uuid := (select auth.uid());
    _org uuid;
    _kit public.brand_kits%rowtype;
    _rule_count int;
begin
    -- 1. Authenticate
    if _uid is null then
        raise exception 'unauthenticated';
    end if;

    -- 2. Get kit
    select * into _kit
    from public.brand_kits
    where id = _kit_id;

    if not found then
        raise exception 'not_found';
    end if;

    _org := _kit.org_id;

    -- 3. Validate membership and role
    if not private.has_role(_org, 'owner') then
        raise exception 'forbidden';
    end if;

    -- 4. Check kit is draft
    if _kit.status <> 'draft' then
        raise exception 'conflict:not_draft_kit';
    end if;

    -- 5. Check kit has at least one rule
    select count(*) into _rule_count
    from public.rules
    where kit_id = _kit_id;

    if _rule_count = 0 then
        raise exception 'conflict:empty_kit';
    end if;

    -- 6. Archive previous active kit
    update public.brand_kits
    set status = 'archived'
    where org_id = _org and status = 'active';

    -- 7. Activate this kit
    update public.brand_kits
    set status = 'active', activated_at = now()
    where id = _kit_id;

    -- 8. Audit log
    insert into public.audit_log (org_id, actor_id, action, entity_type, entity_id)
    values (_org, _uid, 'kit.activated', 'brand_kit', _kit_id);
end $$;

revoke all on function public.activate_kit(uuid) from public, anon;
grant execute on function public.activate_kit(uuid) to authenticated;

-- ============================================================
-- 11. Service-only function: engine_complete_review
-- This is called ONLY by the review service (service role key)
-- Execute permission is granted only to service_role
-- ============================================================
create or replace function public.engine_complete_review(
    _review_id uuid,
    _status public.review_status,
    _llm_status public.llm_status,
    _warnings jsonb,
    _llm_findings_raw int,
    _llm_findings_dropped int,
    _validator_stats jsonb,
    _model text,
    _prompt_version text,
    _findings jsonb
)
returns void
language plpgsql security definer set search_path = ''
as $$
declare
    _review public.reviews%rowtype;
    _finding jsonb;
    _rule_id uuid;
    _fact_id uuid;
begin
    -- 1. Get review row (locked for update)
    select * into _review
    from public.reviews
    where id = _review_id
    for update;

    if not found then
        raise exception 'not_found';
    end if;

    -- 2. Update review row
    update public.reviews
    set status = _status,
        llm_status = _llm_status,
        warnings = _warnings,
        llm_findings_raw = _llm_findings_raw,
        llm_findings_dropped = _llm_findings_dropped,
        validator_stats = _validator_stats,
        model = _model,
        prompt_version = _prompt_version,
        finished_at = now()
    where id = _review_id;

    -- 3. If status is done, insert findings
    if _status = 'done' then
        for _finding in select * from jsonb_array_elements(_findings)
        loop
            -- Resolve rule_id or fact_id from ref_key
            _rule_id := null;
            _fact_id := null;

            if (_finding->>'source') = 'deterministic' then
                select id into _rule_id
                from public.rules
                where kit_id = _review.kit_id and rule_key = _finding->>'ref_key';
            else
                -- Check both rules and facts for llm findings
                select id into _rule_id
                from public.rules
                where kit_id = _review.kit_id and rule_key = _finding->>'ref_key';

                if _rule_id is null then
                    select id into _fact_id
                    from public.approved_facts
                    where kit_id = _review.kit_id and fact_key = _finding->>'ref_key';
                end if;
            end if;

            if _rule_id is null and _fact_id is null then
                -- This should not happen if validator worked, but guard anyway
                raise exception 'unknown_ref';
            end if;

            insert into public.findings (
                org_id, review_id, source, rule_id, fact_id, ref_key,
                category, severity, quote, start_offset, end_offset,
                explanation, suggestion, confidence, needs_human, needs_reviewer
            ) values (
                _review.org_id,
                _review_id,
                (_finding->>'source')::public.finding_source,
                _rule_id,
                _fact_id,
                _finding->>'ref_key',
                (_finding->>'category')::public.rule_category,
                (_finding->>'severity')::public.severity,
                _finding->>'quote',
                (_finding->>'start_offset')::int,
                (_finding->>'end_offset')::int,
                _finding->>'explanation',
                nullif(_finding->>'suggestion', ''),
                case when _finding->>'confidence' is not null then (_finding->>'confidence')::numeric(3,2) end,
                coalesce((_finding->>'needs_human')::boolean, false),
                coalesce((_finding->>'needs_reviewer')::boolean, false)
            );
        end loop;
    end if;

    -- 4. Audit log (actor_id = null for service-role calls)
    insert into public.audit_log (org_id, actor_id, action, entity_type, entity_id, detail)
    values (_review.org_id, null, 'review.completed', 'review', _review_id, jsonb_build_object('status', _status, 'llm_status', _llm_status));
end $$;

-- Service-only function: engine_fail_review
create or replace function public.engine_fail_review(
    _review_id uuid,
    _error text
)
returns void
language plpgsql security definer set search_path = ''
as $$
declare
    _review public.reviews%rowtype;
begin
    select * into _review
    from public.reviews
    where id = _review_id
    for update;

    if not found then
        raise exception 'not_found';
    end if;

    update public.reviews
    set status = 'failed',
        error = _error,
        finished_at = now()
    where id = _review_id;

    insert into public.audit_log (org_id, actor_id, action, entity_type, entity_id, detail)
    values (_review.org_id, null, 'review.failed', 'review', _review_id, jsonb_build_object('error', _error));
end $$;

-- Revoke from public/anon/authenticated, grant only to service_role
revoke all on function public.engine_complete_review(uuid,public.review_status,public.llm_status,jsonb,int,int,jsonb,text,text,jsonb) from public, anon, authenticated;
revoke all on function public.engine_fail_review(uuid,text) from public, anon, authenticated;

-- Grant execute to service_role (the review service uses this role)
-- Migration runs as postgres superuser (local) or Supabase migration runner (production), both can grant to service_role
grant execute on function public.engine_complete_review(uuid,public.review_status,public.llm_status,jsonb,int,int,jsonb,text,text,jsonb) to service_role;
grant execute on function public.engine_fail_review(uuid,text) to service_role;
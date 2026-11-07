-- Migration: 20261108000001_fix_revision_version_ambiguity.sql
-- Description: Fix column reference "version" ambiguity in create_revision and apply_decisions
-- The output parameter "version" in RETURNS TABLE conflicts with unqualified "public.revisions.version" references

-- ============================================================
-- 1. Fix create_revision: qualify all public.references.version column references
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
    order by public.revisions.version desc
    limit 1;

    if _latest_body = _body then
        raise exception 'validation:body';
    end if;

    -- 7. Get next version
    select coalesce(max(public.revisions.version), 0) + 1 into _new_version
    from public.revisions
    where content_id = _content_id;

    -- 8. Insert new revision
    insert into public.revisions (content_id, version, parent_revision_id, body, source, created_by)
    select _content_id, _new_version, id, _body, 'manual', _uid
    from public.revisions
    where content_id = _content_id
    order by public.revisions.version desc
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
-- 2. Fix apply_decisions: qualify all public.references.version column references
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
    _applied_decision_ids uuid[] := '{}';
    _covered_ranges int4range[] := '{}';
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

    -- 5. Get latest revision and its review (enforce latest revision via v_latest_revision)
    select r.id, r.revision_id
    into _latest_review_id, _latest_revision_id
    from public.reviews r
    join public.revisions rv on rv.id = r.revision_id
    join public.v_latest_revision vlr on vlr.revision_id = rv.id
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

    -- 7. Collect pending decisions from latest review
    -- Use DISTINCT ON to get only the latest decision per finding (ordered by created_at DESC, id DESC)
    -- Then filter to only accept/edit decisions that haven't been applied
    -- Order by start_offset DESC so we apply from end to beginning (offsets stay valid)
    for _decision_record in
        select d.id as decision_id,
               d.action,
               d.edited_text,
               f.quote,
               f.start_offset,
               f.end_offset,
               f.suggestion,
               f.id as finding_id
        from (
            select distinct on (d.finding_id) d.id, d.action, d.edited_text, d.finding_id
            from public.decisions d
            join public.findings f on f.id = d.finding_id
            where f.review_id = _latest_review_id
              and d.resulting_revision_id is null
              and d.user_id = _uid
            order by d.finding_id, d.created_at desc, d.id desc
        ) d
        join public.findings f on f.id = d.finding_id
        where d.action in ('accept', 'edit')
        order by f.start_offset desc
    loop
        _quote_start := _decision_record.start_offset;
        _quote_end := _decision_record.end_offset;

        -- Validate offset bounds against the current body.
        if _quote_start < 0
           or _quote_end > length(_new_body)
           or _quote_start >= _quote_end then

            _skip_record := jsonb_build_object(
                'decision_id', _decision_record.decision_id,
                'finding_id', _decision_record.finding_id,
                'reason', 'text_changed'
            );

            _skipped := _skipped || _skip_record;
            continue;
        end if;

        -- Detect overlap BEFORE quote validation.
        -- Ranges use half-open [start, end) semantics.
        if exists (
            select 1
            from unnest(_covered_ranges) as r
            where r && int4range(_quote_start, _quote_end, '[)')
        ) then

            _skip_record := jsonb_build_object(
                'decision_id', _decision_record.decision_id,
                'finding_id', _decision_record.finding_id,
                'reason', 'overlap'
            );

            _skipped := _skipped || _skip_record;
            continue;
        end if;

        -- Validate the original quote at its original offsets.
        if substring(
            _new_body
            from _quote_start + 1
            for _quote_end - _quote_start
        ) <> _decision_record.quote then

            _skip_record := jsonb_build_object(
                'decision_id', _decision_record.decision_id,
                'finding_id', _decision_record.finding_id,
                'reason', 'text_changed'
            );

            _skipped := _skipped || _skip_record;
            continue;
        end if;

        -- Determine replacement text.
        if _decision_record.action = 'accept' then
            _replacement_text := _decision_record.suggestion;
        else
            _replacement_text := _decision_record.edited_text;
        end if;

        -- Apply replacement using zero-based, half-open offsets.
        _new_body :=
            substring(_new_body from 1 for _quote_start)
            || _replacement_text
            || substring(_new_body from _quote_end + 1);

        -- Track only successfully applied decisions and their ranges.
        _applied_decision_ids :=
            array_append(_applied_decision_ids, _decision_record.decision_id);

        _covered_ranges :=
            array_append(
                _covered_ranges,
                int4range(_quote_start, _quote_end, '[)')
            );

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
    select coalesce(max(public.revisions.version), 0) + 1 into _new_version
    from public.revisions
    where content_id = _content_id;

    -- 11. Insert new revision
    insert into public.revisions (content_id, version, parent_revision_id, body, source, created_by)
    values (_content_id, _new_version, _latest_revision_id, _new_body, 'accepted_suggestion', _uid)
    returning id into _new_revision_id;

    -- 12. Update ONLY successfully applied decisions with resulting_revision_id
    update public.decisions d
    set resulting_revision_id = _new_revision_id
    from unnest(_applied_decision_ids) as aid(decision_id)
    where d.id = aid.decision_id;

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
-- 3. Fix clone_kit: qualify public.brand_kits.version column reference
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
    select coalesce(max(public.brand_kits.version), 0) + 1 into _new_version
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
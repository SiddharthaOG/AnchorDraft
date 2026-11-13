-- Fix ambiguous output-column reference in the suggestion acceptance RPC.
-- RETURNS TABLE includes an output variable named status; qualify brand_kits.status
-- in SELECT/UPDATE statements to avoid PL/pgSQL variable/column ambiguity.

create or replace function public.accept_guideline_suggestion(
    _suggestion_id uuid,
    _actor_id uuid
)
returns table (kit_id uuid, version integer, status text)
language plpgsql
security definer
set search_path = ''
as $$
declare
    _suggestion public.guideline_suggestions%rowtype;
    _source public.brand_kits%rowtype;
    _active public.brand_kits%rowtype;
    _current_text text;
    _new_version integer;
    _new_kit_id uuid;
begin
    if _actor_id is null then raise exception 'unauthenticated'; end if;

    select * into _suggestion
      from public.guideline_suggestions
     where id = _suggestion_id
     for update;
    if not found then raise exception 'not_found'; end if;

    if not exists (
        select 1
          from public.memberships m
         where m.org_id = _suggestion.org_id
           and m.user_id = _actor_id
           and (
             m.roles @> array['manager'::public.app_role]
             or m.roles @> array['owner'::public.app_role]
           )
    ) then
        raise exception 'forbidden';
    end if;

    if _suggestion.status <> 'pending' then
        raise exception 'conflict:suggestion_not_pending';
    end if;

    -- Same lock used by clone_kit; serializes every version allocator.
    perform 1 from public.organizations where id = _suggestion.org_id for update;

    select * into _source
      from public.brand_kits
     where id = _suggestion.source_kit_id;
    if not found then
        update public.guideline_suggestions
           set status = 'stale', resolved_by = _actor_id, resolved_at = now()
         where id = _suggestion_id;
        return query select null::uuid, null::integer, 'stale'::text;
        return;
    end if;

    -- Qualify status because RETURNS TABLE exposes an output variable named status.
    select bk.* into _active
      from public.brand_kits as bk
     where bk.org_id = _suggestion.org_id and bk.status = 'active'
     for update of bk;

    select r.guideline_text into _current_text
      from public.rules r
     where r.kit_id = _active.id and r.rule_key = _suggestion.rule_key
     for update;

    if _active.id is null
       or _active.id <> _suggestion.source_kit_id
       or _active.version <> _suggestion.source_kit_version
       or _current_text is distinct from _suggestion.source_guideline_text then
        update public.guideline_suggestions
           set status = 'stale', resolved_by = _actor_id, resolved_at = now()
         where id = _suggestion_id;
        return query select null::uuid, null::integer, 'stale'::text;
        return;
    end if;

    select coalesce(max(b.version), 0) + 1 into _new_version
      from public.brand_kits b
     where b.org_id = _suggestion.org_id;

    insert into public.brand_kits (org_id, version, name, status, source_kit_id, created_by)
    values (_suggestion.org_id, _new_version, _source.name || ' (guideline update)',
            'draft', _source.id, _actor_id)
    returning id into _new_kit_id;

    insert into public.rules (
        kit_id, rule_key, category, title, guideline_text, severity,
        check_kind, config, needs_reviewer, example_bad, example_good
    )
    select _new_kit_id, rule_key, category, title, guideline_text, severity,
           check_kind, config, needs_reviewer, example_bad, example_good
      from public.rules where kit_id = _source.id;

    insert into public.approved_facts (kit_id, fact_key, statement, source_note, valid_until)
    select _new_kit_id, fact_key, statement, source_note, valid_until
      from public.approved_facts where kit_id = _source.id;

    update public.rules
       set guideline_text = _suggestion.suggested_text
     where kit_id = _new_kit_id and rule_key = _suggestion.rule_key;
    if not found then raise exception 'conflict:source_rule_missing'; end if;

    update public.brand_kits as bk
       set status = 'archived'
     where bk.org_id = _suggestion.org_id and bk.status = 'active';

    update public.brand_kits as bk
       set status = 'active', activated_at = now()
     where bk.id = _new_kit_id;

    update public.guideline_suggestions
       set status = 'accepted', resolved_by = _actor_id, resolved_at = now(),
           accepted_kit_id = _new_kit_id
     where id = _suggestion_id;

    insert into public.audit_log (org_id, actor_id, action, entity_type, entity_id, detail)
    values (
        _suggestion.org_id, _actor_id, 'guideline_suggestion.accepted',
        'guideline_suggestion', _suggestion_id,
        jsonb_build_object(
            'source_kit_id', _source.id,
            'source_version', _source.version,
            'accepted_kit_id', _new_kit_id,
            'accepted_version', _new_version,
            'rule_key', _suggestion.rule_key
        )
    );

    return query select _new_kit_id, _new_version, 'accepted'::text;
end;
$$;

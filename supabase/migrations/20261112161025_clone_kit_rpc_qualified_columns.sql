-- Qualify source kit_id references in clone_kit. The RETURNS TABLE
-- output parameter kit_id otherwise conflicts with the source table column.

create or replace function public.clone_kit(_kit_id uuid)
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
    if _uid is null then raise exception 'unauthenticated'; end if;

    select * into _source_kit
    from public.brand_kits
    where id = _kit_id;
    if not found then raise exception 'not_found'; end if;

    _org := _source_kit.org_id;
    if not private.has_role(_org, 'owner') then raise exception 'forbidden'; end if;

    perform 1 from public.organizations where id = _org for update;

    select coalesce(max(public.brand_kits.version), 0) + 1
      into _new_version
      from public.brand_kits
     where org_id = _org;

    insert into public.brand_kits (org_id, version, name, status, source_kit_id, created_by)
    values (_org, _new_version, _source_kit.name || ' (copy)', 'draft', _kit_id, _uid)
    returning id into _new_kit_id;

    insert into public.rules (
        kit_id, rule_key, category, title, guideline_text, severity,
        check_kind, config, needs_reviewer, example_bad, example_good
    )
    select _new_kit_id, source_rule.rule_key, source_rule.category,
           source_rule.title, source_rule.guideline_text, source_rule.severity,
           source_rule.check_kind, source_rule.config, source_rule.needs_reviewer,
           source_rule.example_bad, source_rule.example_good
      from public.rules as source_rule
     where source_rule.kit_id = _kit_id;

    insert into public.approved_facts (kit_id, fact_key, statement, source_note, valid_until)
    select _new_kit_id, source_fact.fact_key, source_fact.statement,
           source_fact.source_note, source_fact.valid_until
      from public.approved_facts as source_fact
     where source_fact.kit_id = _kit_id;

    insert into public.audit_log (org_id, actor_id, action, entity_type, entity_id, detail)
    values (_org, _uid, 'kit.cloned', 'brand_kit', _new_kit_id,
            jsonb_build_object('source_kit_id', _kit_id, 'version', _new_version));

    return query select _new_kit_id, _new_version;
end;
$$;

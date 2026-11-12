-- Improvement 3: version-aware guideline-gap analytics and human-governed suggestions.

create table if not exists public.guideline_suggestions (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations(id) on delete cascade,
    source_kit_id uuid not null references public.brand_kits(id) on delete restrict,
    source_kit_version integer not null check (source_kit_version > 0),
    rule_key text not null,
    source_guideline_text text not null,
    source_guideline_hash text not null check (length(source_guideline_hash) = 64),
    suggested_text text not null check (length(btrim(suggested_text)) between 1 and 500),
    explanation text not null check (length(btrim(explanation)) between 1 and 1000),
    evidence jsonb not null default '{}'::jsonb,
    status text not null default 'pending'
        check (status in ('pending', 'accepted', 'rejected', 'stale')),
    created_by uuid not null references auth.users(id),
    created_at timestamptz not null default now(),
    resolved_by uuid references auth.users(id),
    resolved_at timestamptz,
    rejection_reason text,
    accepted_kit_id uuid references public.brand_kits(id) on delete set null,
    provider text,
    model text,
    prompt_version text not null default 'guideline-reword-v1'
);

create unique index if not exists guideline_suggestions_one_pending_per_rule
    on public.guideline_suggestions (org_id, source_kit_id, rule_key)
    where status = 'pending';
create index if not exists guideline_suggestions_org_status_created
    on public.guideline_suggestions (org_id, status, created_at desc);

create table if not exists public.guideline_suggestion_previews (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    source_kit_id uuid not null references public.brand_kits(id) on delete cascade,
    rule_key text not null,
    source_guideline_hash text not null check (length(source_guideline_hash) = 64),
    policy_version integer not null check (policy_version > 0),
    policy_sha256 text not null check (length(policy_sha256) = 64),
    payload_sha256 text not null check (length(payload_sha256) = 64),
    provider_request jsonb not null,
    evidence jsonb not null default '{}'::jsonb,
    reverse_map_ciphertext text not null default '',
    redaction_summary jsonb not null default '{}'::jsonb,
    token_hash text not null unique check (length(token_hash) = 64),
    expires_at timestamptz not null,
    consumed_at timestamptz,
    created_at timestamptz not null default now()
);

create index if not exists guideline_suggestion_previews_expiry
    on public.guideline_suggestion_previews (expires_at)
    where consumed_at is null;

alter table public.guideline_suggestions enable row level security;
alter table public.guideline_suggestion_previews enable row level security;

drop policy if exists guideline_suggestions_manager_read on public.guideline_suggestions;
create policy guideline_suggestions_manager_read
    on public.guideline_suggestions
    for select to authenticated
    using (
        private.has_role(org_id, 'manager')
        or private.has_role(org_id, 'owner')
    );

-- Preview payloads and encrypted reverse maps are backend-only.
revoke all on public.guideline_suggestion_previews from public, anon, authenticated;
grant all on public.guideline_suggestion_previews to service_role;

-- Suggestions are read-only from the browser. All state transitions go through
-- narrowly scoped, service-role-only RPCs after API authentication.
revoke all on public.guideline_suggestions from public, anon, authenticated;
grant select on public.guideline_suggestions to authenticated;
grant all on public.guideline_suggestions to service_role;

-- Serialize all normal kit clones on the organization row. This closes the
-- MAX(version)+1 race without changing the existing owner-only permission.
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
    select _new_kit_id, rule_key, category, title, guideline_text, severity,
           check_kind, config, needs_reviewer, example_bad, example_good
      from public.rules where kit_id = _kit_id;

    insert into public.approved_facts (kit_id, fact_key, statement, source_note, valid_until)
    select _new_kit_id, fact_key, statement, source_note, valid_until
      from public.approved_facts where kit_id = _kit_id;

    insert into public.audit_log (org_id, actor_id, action, entity_type, entity_id, detail)
    values (_org, _uid, 'kit.cloned', 'brand_kit', _new_kit_id,
            jsonb_build_object('source_kit_id', _kit_id, 'version', _new_version));

    return query select _new_kit_id, _new_version;
end;
$$;

revoke all on function public.clone_kit(uuid) from public, anon;
grant execute on function public.clone_kit(uuid) to authenticated;

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

    select * into _active
      from public.brand_kits
     where org_id = _suggestion.org_id and status = 'active'
     for update;

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

    update public.brand_kits
       set status = 'archived'
     where org_id = _suggestion.org_id and status = 'active';

    update public.brand_kits
       set status = 'active', activated_at = now()
     where id = _new_kit_id;

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

create or replace function public.reject_guideline_suggestion(
    _suggestion_id uuid,
    _actor_id uuid,
    _reason text default null
)
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
    _suggestion public.guideline_suggestions%rowtype;
begin
    if _actor_id is null then raise exception 'unauthenticated'; end if;
    if _reason is not null and length(_reason) > 1000 then
        raise exception 'validation:reason';
    end if;

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

    update public.guideline_suggestions
       set status = 'rejected', resolved_by = _actor_id, resolved_at = now(),
           rejection_reason = nullif(btrim(_reason), '')
     where id = _suggestion_id;

    insert into public.audit_log (org_id, actor_id, action, entity_type, entity_id, detail)
    values (
        _suggestion.org_id, _actor_id, 'guideline_suggestion.rejected',
        'guideline_suggestion', _suggestion_id,
        jsonb_build_object('rule_key', _suggestion.rule_key, 'has_reason', nullif(btrim(_reason), '') is not null)
    );

    return 'rejected';
end;
$$;

revoke all on function public.accept_guideline_suggestion(uuid, uuid) from public, anon, authenticated;
revoke all on function public.reject_guideline_suggestion(uuid, uuid, text) from public, anon, authenticated;
grant execute on function public.accept_guideline_suggestion(uuid, uuid) to service_role;
grant execute on function public.reject_guideline_suggestion(uuid, uuid, text) to service_role;

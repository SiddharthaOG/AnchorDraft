-- Migration: 20261112000001_visual_asset_content_link.sql
-- Description: Create junction table linking visual assets to content/revisions

-- 1. Junction table linking visual assets to content
create table public.visual_asset_contents (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations(id) on delete cascade,
    visual_asset_id uuid not null references public.visual_assets(id) on delete cascade,
    content_id uuid not null references public.contents(id) on delete cascade,
    revision_id uuid references public.revisions(id) on delete cascade,
    uploaded_by uuid not null references auth.users(id) on delete restrict,
    created_at timestamptz not null default now(),
    constraint visual_asset_contents_unique unique (visual_asset_id, content_id)
);

-- Indexes for visual_asset_contents
create index idx_visual_asset_contents_org_id on public.visual_asset_contents (org_id);
create index idx_visual_asset_contents_visual_asset_id on public.visual_asset_contents (visual_asset_id);
create index idx_visual_asset_contents_content_id on public.visual_asset_contents (content_id);
create index idx_visual_asset_contents_revision_id on public.visual_asset_contents (revision_id);

-- RLS policies for visual_asset_contents
alter table public.visual_asset_contents enable row level security;

create policy visual_asset_contents_select on public.visual_asset_contents
    for select to authenticated
    using (private.is_member(org_id));

create policy visual_asset_contents_insert on public.visual_asset_contents
    for insert to authenticated
    with check (
        private.is_member(org_id)
        and uploaded_by = (select auth.uid())
    );

-- 2. RPC function to link visual asset to content/revision
create or replace function public.link_visual_asset_to_content(
    _visual_asset_id uuid,
    _content_id uuid,
    _revision_id uuid default null
)
returns void
language plpgsql security definer set search_path = ''
as $$
declare
    _uid uuid := (select auth.uid());
    _org_id uuid;
    _visual_asset_org uuid;
    _content_org uuid;
    _revision_content_id uuid;
begin
    -- 1. Authenticate
    if _uid is null then
        raise exception 'unauthenticated';
    end if;

    -- 2. Get visual asset org
    select org_id into _visual_asset_org
    from public.visual_assets
    where id = _visual_asset_id;

    if not found then
        raise exception 'not_found: visual_asset';
    end if;

    -- 3. Get content org and verify access
    select org_id into _content_org
    from public.contents
    where id = _content_id;

    if not found then
        raise exception 'not_found: content';
    end if;

    if _visual_asset_org <> _content_org then
        raise exception 'forbidden: cross-organization asset linking';
    end if;

    if not private.is_member(_content_org) then
        raise exception 'forbidden: not member of content org';
    end if;

    -- 4. If revision_id provided, verify it belongs to the content
    if _revision_id is not null then
        select content_id into _revision_content_id
        from public.revisions
        where id = _revision_id;

        if not found then
            raise exception 'not_found: revision';
        end if;

        if _revision_content_id <> _content_id then
            raise exception 'conflict: revision does not belong to content';
        end if;
    end if;

    -- 5. Insert link (idempotent via unique constraint)
    insert into public.visual_asset_contents (org_id, visual_asset_id, content_id, revision_id, uploaded_by)
    values (_content_org, _visual_asset_id, _content_id, _revision_id, _uid)
    on conflict (visual_asset_id, content_id) do nothing;

    -- 6. Audit log
    insert into public.audit_log (org_id, actor_id, action, entity_type, entity_id, detail)
    values (_content_org, _uid, 'visual_asset.linked', 'visual_asset', _visual_asset_id,
        jsonb_build_object('content_id', _content_id, 'revision_id', _revision_id));
end $$;

revoke all on function public.link_visual_asset_to_content(uuid, uuid, uuid) from public, anon;
grant execute on function public.link_visual_asset_to_content(uuid, uuid, uuid) to authenticated;

-- 2. RPC function to get visual assets for a revision
create or replace function public.get_visual_assets_for_revision(
    _revision_id uuid
)
returns setof public.visual_assets
language plpgsql security definer set search_path = ''
as $$
declare
    _uid uuid := (select auth.uid());
    _revision public.revisions%rowtype;
    _content_org uuid;
begin
    if _uid is null then
        raise exception 'unauthenticated';
    end if;

    select * into _revision
    from public.revisions
    where id = _revision_id;

    if not found then
        raise exception 'not_found';
    end if;

    select org_id into _content_org
    from public.contents
    where id = _revision.content_id;

    if not private.is_member(_content_org) then
        raise exception 'forbidden';
    end if;

    return query
    select va.*
    from public.visual_assets va
    join public.visual_asset_contents vac on vac.visual_asset_id = va.id
    where vac.revision_id = _revision_id
    order by va.created_at desc;
end $$;

revoke all on function public.get_visual_assets_for_revision(uuid) from public, anon;
grant execute on function public.get_visual_assets_for_revision(uuid) to authenticated;

-- 3. RPC function to get visual assets for a content
create or replace function public.get_visual_assets_for_content(
    _content_id uuid
)
returns setof public.visual_assets
language plpgsql security definer set search_path = ''
as $$
declare
    _uid uuid := (select auth.uid());
    _content_org uuid;
begin
    if _uid is null then
        raise exception 'unauthenticated';
    end if;

    select org_id into _content_org
    from public.contents
    where id = _content_id;

    if not found then
        raise exception 'not_found';
    end if;

    if not private.is_member(_content_org) then
        raise exception 'forbidden';
    end if;

    return query
    select va.*
    from public.visual_assets va
    join public.visual_asset_contents vac on vac.visual_asset_id = va.id
    where vac.content_id = _content_id
    order by va.created_at desc;
end $$;

revoke all on function public.get_visual_assets_for_content(uuid) from public, anon;
grant execute on function public.get_visual_assets_for_content(uuid) to authenticated;

-- Grant execute permissions
revoke all on function public.link_visual_asset_to_content(uuid, uuid, uuid) from public, anon;
grant execute on function public.link_visual_asset_to_content(uuid, uuid, uuid) to authenticated;

revoke all on function public.get_visual_assets_for_revision(uuid) from public, anon;
grant execute on function public.get_visual_assets_for_revision(uuid) to authenticated;

revoke all on function public.get_visual_assets_for_content(uuid) from public, anon;
grant execute on function public.get_visual_assets_for_content(uuid) to authenticated;
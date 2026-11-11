-- Forward-only hardening for visual asset ownership, linking, cleanup, and Storage.
-- Backend RPCs use service_role and receive the authenticated actor explicitly.

create or replace function public.create_visual_asset(
    _org_id uuid,
    _actor_user_id uuid,
    _storage_path text,
    _mime_type text,
    _width int,
    _height int,
    _checksum text,
    _metadata jsonb default '{}'::jsonb
) returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
    _asset_id uuid;
    _requested_asset_id uuid;
    _created boolean := false;
begin
    if _actor_user_id is null then raise exception 'unauthenticated: actor required'; end if;
    if _org_id is null or _storage_path is null
       or split_part(_storage_path, '/', 1) <> _org_id::text
       or split_part(_storage_path, '/', 2) = ''
       or split_part(_storage_path, '/', 3) <> '' then
        raise exception 'validation: storage path must be <org_uuid>/<asset_uuid>.<extension>';
    end if;
    begin
        _requested_asset_id := split_part(split_part(_storage_path, '/', 2), '.', 1)::uuid;
    exception when others then
        raise exception 'validation: storage filename must begin with an asset UUID';
    end;
    if _mime_type not in ('image/png','image/jpeg','image/webp') then
        raise exception 'validation: unsupported visual asset MIME type';
    end if;
    if _storage_path <> _org_id::text || '/' || _requested_asset_id::text ||
       case _mime_type when 'image/png' then '.png' when 'image/jpeg' then '.jpg' else '.webp' end then
        raise exception 'validation: storage filename extension or asset UUID mismatch';
    end if;
    if _width is null or _width <= 0 or _height is null or _height <= 0 then
        raise exception 'validation: image dimensions must be positive';
    end if;
    if _checksum is null or btrim(_checksum) = '' then
        raise exception 'validation: checksum is required';
    end if;
    if _metadata is null or jsonb_typeof(_metadata) <> 'object' then
        raise exception 'validation: metadata must be a JSON object';
    end if;
    if not exists (
        select 1 from public.memberships m
        where m.org_id = _org_id and m.user_id = _actor_user_id
          and (m.roles && array['creator','owner']::public.app_role[])
    ) then
        raise exception 'forbidden: creator or owner role required';
    end if;

    insert into public.visual_assets
        (id, org_id, storage_path, mime_type, width, height, checksum, uploaded_by, metadata)
    values
        (_requested_asset_id, _org_id, _storage_path, _mime_type, _width, _height, _checksum, _actor_user_id, _metadata)
    on conflict (org_id, checksum) do nothing
    returning id into _asset_id;

    if _asset_id is not null then
        _created := true;
    else
        select id into _asset_id
        from public.visual_assets
        where org_id = _org_id and checksum = _checksum
        for share;
        if _asset_id is null then
            raise exception 'conflict: checksum collision could not be resolved';
        end if;
    end if;

    insert into public.audit_log (org_id, actor_id, action, entity_type, entity_id, detail)
    values (_org_id, _actor_user_id, 'visual_asset.upload', 'visual_asset', _asset_id,
            jsonb_build_object('created', _created, 'reused', not _created, 'checksum', _checksum));
    return _asset_id;
end $$;

revoke all on function public.create_visual_asset(uuid,uuid,text,text,int,int,text,jsonb) from public, anon, authenticated;
grant execute on function public.create_visual_asset(uuid,uuid,text,text,int,int,text,jsonb) to service_role;
-- Retire the historical auth.uid()-dependent overload.
revoke all on function public.create_visual_asset(uuid,text,text,int,int,text,jsonb) from public, anon, authenticated;
drop function if exists public.create_visual_asset(uuid,text,text,int,int,text,jsonb);

create or replace function public.link_visual_asset_to_content(
    _visual_asset_id uuid,
    _content_id uuid,
    _actor_user_id uuid,
    _revision_id uuid default null
) returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
    _asset_org uuid;
    _content_org uuid;
    _existing_revision uuid;
    _revision_content uuid;
begin
    if _actor_user_id is null then raise exception 'unauthenticated'; end if;
    select org_id into _asset_org from public.visual_assets where id = _visual_asset_id;
    if not found then raise exception 'not_found: visual_asset'; end if;
    select org_id into _content_org from public.contents where id = _content_id;
    if not found then raise exception 'not_found: content'; end if;
    if _asset_org <> _content_org then raise exception 'forbidden: cross-organization link'; end if;
    if not exists (
        select 1 from public.memberships m
        where m.org_id = _content_org and m.user_id = _actor_user_id
          and (m.roles && array['creator','owner']::public.app_role[])
    ) then
        raise exception 'forbidden: creator or owner role required';
    end if;
    if _revision_id is not null then
        select content_id into _revision_content from public.revisions where id = _revision_id;
        if not found then raise exception 'not_found: revision'; end if;
        if _revision_content <> _content_id then
            raise exception 'conflict: revision does not belong to content';
        end if;
    end if;

    insert into public.visual_asset_contents
        (org_id, visual_asset_id, content_id, revision_id, uploaded_by)
    values (_content_org, _visual_asset_id, _content_id, _revision_id, _actor_user_id)
    on conflict (visual_asset_id, content_id) do nothing;
    if not found then
        select revision_id into _existing_revision
        from public.visual_asset_contents
        where visual_asset_id = _visual_asset_id and content_id = _content_id
        for update;
        if not found or _existing_revision is distinct from _revision_id then
            raise exception 'conflict: asset is already linked to this content at a different revision';
        end if;
    end if;

    insert into public.audit_log (org_id, actor_id, action, entity_type, entity_id, detail)
    values (_content_org, _actor_user_id, 'visual_asset.linked', 'visual_asset', _visual_asset_id,
            jsonb_build_object('content_id', _content_id, 'revision_id', _revision_id));
end $$;

revoke all on function public.link_visual_asset_to_content(uuid,uuid,uuid,uuid) from public, anon, authenticated;
grant execute on function public.link_visual_asset_to_content(uuid,uuid,uuid,uuid) to service_role;

-- The ownership/link checks and row deletion are one database transaction.
-- Storage deletion is performed by the backend only after this RPC returns the exact path.
create or replace function public.cleanup_new_visual_asset(
    _org_id uuid,
    _asset_id uuid,
    _storage_path text,
    _actor_user_id uuid
) returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
    _actual_path text;
begin
    if _actor_user_id is null then raise exception 'unauthenticated: cleanup actor required'; end if;
    select storage_path into _actual_path
    from public.visual_assets
    where id = _asset_id and org_id = _org_id and uploaded_by = _actor_user_id
    for update;
    if not found then return null; end if;
    if _actual_path <> _storage_path then
        raise exception 'forbidden: storage path does not belong to asset';
    end if;
    if exists (select 1 from public.visual_asset_contents where visual_asset_id = _asset_id)
       or exists (select 1 from public.findings where asset_id = _asset_id) then
        raise exception 'conflict: cannot clean up an asset referenced by content or findings';
    end if;
    delete from public.visual_assets where id = _asset_id and org_id = _org_id and storage_path = _storage_path;
    return _actual_path;
end $$;
revoke all on function public.cleanup_new_visual_asset(uuid,uuid,text,uuid) from public, anon, authenticated;
grant execute on function public.cleanup_new_visual_asset(uuid,uuid,text,uuid) to service_role;

-- Prevent direct authenticated writes from bypassing the service-role RPC contracts.
drop policy if exists visual_assets_insert on public.visual_assets;
drop policy if exists visual_asset_contents_insert on public.visual_asset_contents;
revoke insert, update, delete on public.visual_assets from anon, authenticated;
revoke insert, update, delete on public.visual_asset_contents from anon, authenticated;

-- Harden the revision listing RPC against historical/corrupt cross-org link rows.
create or replace function public.get_visual_assets_for_revision(
    _revision_id uuid,
    _org_id uuid
) returns setof public.visual_assets
language plpgsql
security definer
set search_path = ''
as $$
declare
    _revision public.revisions%rowtype;
    _content_org uuid;
begin
    select * into _revision from public.revisions where id = _revision_id;
    if not found then raise exception 'not_found: revision'; end if;
    select org_id into _content_org from public.contents where id = _revision.content_id;
    if not found then raise exception 'not_found: content'; end if;
    if _content_org <> _org_id then raise exception 'forbidden: revision organization mismatch'; end if;
    return query
    select va.*
    from public.visual_assets va
    join public.visual_asset_contents vac
      on vac.visual_asset_id = va.id
     and vac.org_id = _org_id
     and vac.content_id = _revision.content_id
     and vac.revision_id = _revision_id
    where va.org_id = _org_id
    order by va.created_at desc;
end $$;
revoke all on function public.get_visual_assets_for_revision(uuid,uuid) from public, anon, authenticated;
grant execute on function public.get_visual_assets_for_revision(uuid,uuid) to service_role;

-- Replace only the policies created by the historical visual-assets migration.
drop policy if exists "visual_assets_upload" on storage.objects;
drop policy if exists "visual_assets_select" on storage.objects;
drop policy if exists "visual_assets_update" on storage.objects;
drop policy if exists "visual_assets_delete" on storage.objects;

create policy "visual_assets_upload" on storage.objects
for insert to authenticated
with check (
    bucket_id = 'visual-assets'
    and split_part(name, '/', 1) ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    and exists (
        select 1 from public.memberships m
        where m.org_id::text = split_part(name, '/', 1)
          and m.user_id = (select auth.uid())
          and (m.roles && array['creator','owner']::public.app_role[])
    )
);
create policy "visual_assets_select" on storage.objects
for select to authenticated
using (
    bucket_id = 'visual-assets'
    and exists (
        select 1 from public.visual_assets va
        join public.memberships m on m.org_id = va.org_id
        where va.storage_path = storage.objects.name
          and m.user_id = (select auth.uid())
    )
);
create policy "visual_assets_update" on storage.objects
for update to authenticated
using (
    bucket_id = 'visual-assets'
    and exists (
        select 1 from public.visual_assets va
        join public.memberships m on m.org_id = va.org_id
        where va.storage_path = storage.objects.name
          and m.user_id = (select auth.uid())
          and (va.uploaded_by = (select auth.uid()) or m.roles && array['owner']::public.app_role[])
    )
)
with check (
    bucket_id = 'visual-assets'
    and exists (
        select 1 from public.visual_assets va
        join public.memberships m on m.org_id = va.org_id
        where va.storage_path = storage.objects.name
          and m.user_id = (select auth.uid())
          and (va.uploaded_by = (select auth.uid()) or m.roles && array['owner']::public.app_role[])
    )
);
create policy "visual_assets_delete" on storage.objects
for delete to authenticated
using (
    bucket_id = 'visual-assets'
    and exists (
        select 1 from public.visual_assets va
        join public.memberships m on m.org_id = va.org_id
        where va.storage_path = storage.objects.name
          and m.user_id = (select auth.uid())
          and (va.uploaded_by = (select auth.uid()) or m.roles && array['owner']::public.app_role[])
    )
);

-- Migration: 20261111000001_visual_assets.sql
-- Description: Create visual_assets table and extend findings with visual evidence

-- 1. Visual assets table
create table public.visual_assets (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations(id) on delete cascade,
    storage_path text not null,           -- e.g., "org-uuid/asset-uuid.png"
    mime_type text not null check (mime_type in ('image/png','image/jpeg','image/webp')),
    width int not null check (width > 0),
    height int not null check (height > 0),
    checksum text not null,               -- SHA-256 for deduplication
    uploaded_by uuid not null references auth.users(id) on delete restrict,
    created_at timestamptz not null default now(),
    metadata jsonb not null default '{}', -- palette, dominant_colors, perceptual_hash, etc.
    constraint visual_assets_org_checksum_unique unique (org_id, checksum)
);

-- Index for visual_assets
create index idx_visual_assets_org_id on public.visual_assets (org_id);
create index idx_visual_assets_checksum on public.visual_assets (checksum);
create index idx_visual_assets_uploaded_by on public.visual_assets (uploaded_by);

-- 2. Extend findings with visual evidence fields
alter table public.findings add column if not exists asset_id uuid null references public.visual_assets(id) on delete set null;
alter table public.findings add column if not exists region jsonb null;  -- {"x": 0, "y": 0, "w": 100, "h": 100} normalized 0-1

create index idx_findings_asset_id on public.findings (asset_id);

-- 3. Add visual guidelines to brand_kits
alter table public.brand_kits add column if not exists visual_guidelines jsonb null default '{}';
-- Example visual_guidelines:
-- {
--   "logo": {
--     "required": true,
--     "variants": ["primary", "monochrome"],
--     "clear_space_ratio": 0.1,
--     "min_size_px": 32,
--     "approved_assets": ["asset-id-1", "asset-id-2"]
--   },
--   "palette": {
--     "colors": [
--       {"name": "primary", "hex": "#0066CC", "tolerance": 10},
--       {"name": "secondary", "hex": "#00AA44", "tolerance": 10}
--     ],
--     "allow_neutrals": true
--   },
--   "contrast": {
--     "min_ratio": 4.5,
--     "level": "AA",
--     "ignore_backgrounds": ["#FFFFFF", "#000000"]
--   }
-- }

-- 4. RLS policies for visual_assets
alter table public.visual_assets enable row level security;

create policy visual_assets_select on public.visual_assets
    for select to authenticated
    using (private.is_member(org_id));

create policy visual_assets_insert on public.visual_assets
    for insert to authenticated
    with check (
        private.is_member(org_id)
        and uploaded_by = (select auth.uid())
    );

-- 5. RPC function to create visual asset
create or replace function public.create_visual_asset(
    _org_id uuid,
    _storage_path text,
    _mime_type text,
    _width int,
    _height int,
    _checksum text,
    _metadata jsonb default '{}'
) returns uuid
language plpgsql security definer set search_path = ''
as $$
declare
    _uid uuid := (select auth.uid());
    _asset_id uuid;
begin
    if _uid is null then
        raise exception 'unauthenticated';
    end if;

    if not private.has_role(_org_id, 'creator') and not private.has_role(_org_id, 'owner') then
        raise exception 'forbidden';
    end if;

    insert into public.visual_assets (org_id, storage_path, mime_type, width, height, checksum, uploaded_by, metadata)
    values (_org_id, _storage_path, _mime_type, _width, _height, _checksum, _uid, _metadata)
    on conflict (org_id, checksum) do update
        set storage_path = excluded.storage_path,
            mime_type = excluded.mime_type,
            width = excluded.width,
            height = excluded.height,
            metadata = excluded.metadata,
            uploaded_by = excluded.uploaded_by
    returning id into _asset_id;

    insert into public.audit_log (org_id, actor_id, action, entity_type, entity_id, detail)
    values (_org_id, _uid, 'visual_asset.upload', 'visual_asset', _asset_id, jsonb_build_object('storage_path', _storage_path, 'mime_type', _mime_type));

    return _asset_id;
end $$;

-- 6. RPC function to get visual asset
create or replace function public.get_visual_asset(_asset_id uuid)
returns setof public.visual_assets
language plpgsql security definer set search_path = ''
as $$
declare
    _uid uuid := (select auth.uid());
    _org_id uuid;
begin
    if _uid is null then
        raise exception 'unauthenticated';
    end if;

    select org_id into _org_id from public.visual_assets where id = _asset_id;
    if not found then
        raise exception 'not_found';
    end if;

    if not private.is_member(_org_id) then
        raise exception 'forbidden';
    end if;

    return query select * from public.visual_assets where id = _asset_id;
end $$;

-- 7. RPC function to list visual assets
create or replace function public.list_visual_assets(
    _org_id uuid,
    _limit int default 50,
    _offset int default 0
)
returns setof public.visual_assets
language plpgsql security definer set search_path = ''
as $$
declare
    _uid uuid := (select auth.uid());
begin
    if _uid is null then
        raise exception 'unauthenticated';
    end if;

    if not private.is_member(_org_id) then
        raise exception 'forbidden';
    end if;

    return query
    select * from public.visual_assets
    where org_id = _org_id
    order by created_at desc
    limit _limit offset _offset;
end $$;

-- 8. RPC function to generate signed URL for visual asset
create or replace function public.get_visual_asset_signed_url(
    _asset_id uuid,
    _expires_in_seconds int default 3600
)
returns text
language plpgsql security definer set search_path = ''
as $$
declare
    _uid uuid := (select auth.uid());
    _storage_path text;
    _org_id uuid;
    _signed_url text;
begin
    if _uid is null then
        raise exception 'unauthenticated';
    end if;

    select storage_path, org_id into _storage_path, _org_id
    from public.visual_assets where id = _asset_id;
    
    if not found then
        raise exception 'not_found';
    end if;

    if not private.is_member(_org_id) then
        raise exception 'forbidden';
    end if;

    -- Generate signed URL using Supabase Storage
    -- This requires the service role key, so we call the storage API
    -- The actual signed URL generation happens in the application layer
    -- This function returns the storage path for the app to generate signed URL
    return _storage_path;
end $$;

-- 9. Grant execute permissions
revoke all on function public.create_visual_asset from public, anon;
grant execute on function public.create_visual_asset to authenticated;

revoke all on function public.get_visual_asset from public, anon;
grant execute on function public.get_visual_asset to authenticated;

revoke all on function public.list_visual_assets from public, anon;
grant execute on function public.list_visual_assets to authenticated;

revoke all on function public.get_visual_asset_signed_url from public, anon;
grant execute on function public.get_visual_asset_signed_url to authenticated;
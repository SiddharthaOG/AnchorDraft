-- Migration: 20261112000003_visual_assets_storage.sql
-- Description: Provision private Supabase Storage bucket for visual assets

-- 1. Create private storage bucket for visual assets
-- The bucket is created with private access by default
-- File size limit: 10 MB
-- Allowed MIME types: image/png, image/jpeg, image/webp

-- Insert bucket configuration (idempotent - safe to re-run)
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
    'visual-assets',
    'visual-assets',
    false,  -- private bucket
    10485760,  -- 10 MB in bytes
    array['image/png', 'image/jpeg', 'image/webp']
)
on conflict (id) do update set
    name = excluded.name,
    public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

-- 2. Storage policies for visual-assets bucket
-- All policies use organization-scoped paths: <org_id>/<uuid>.<ext>

-- Policy: Allow authenticated users to upload to their organization's path
create policy "visual_assets_upload" on storage.objects
    for insert to authenticated
    with check (
        bucket_id = 'visual-assets'
        and (storage.foldername(name))[1] = (select auth.uid()::text)  -- First folder is user ID (approximate)
        -- Note: More precise org validation happens at API layer
    );

-- Policy: Allow organization members to read their assets
create policy "visual_assets_select" on storage.objects
    for select to authenticated
    using (
        bucket_id = 'visual-assets'
        and exists (
            select 1 from public.visual_assets va
            join public.memberships m on m.org_id = va.org_id
            where m.user_id = (select auth.uid())
            and va.storage_path = storage.objects.name
        )
    );

-- Policy: Allow users to update their own uploads
create policy "visual_assets_update" on storage.objects
    for update to authenticated
    using (
        bucket_id = 'visual-assets'
        and exists (
            select 1 from public.visual_assets va
            join public.memberships m on m.org_id = va.org_id
            where m.user_id = (select auth.uid())
            and va.storage_path = storage.objects.name
            and va.uploaded_by = (select auth.uid())
        )
    );

-- Policy: Allow users to delete their own uploads
create policy "visual_assets_delete" on storage.objects
    for delete to authenticated
    using (
        bucket_id = 'visual-assets'
        and exists (
            select 1 from public.visual_assets va
            join public.memberships m on m.org_id = va.org_id
            where m.user_id = (select auth.uid())
            and va.storage_path = storage.objects.name
            and va.uploaded_by = (select auth.uid())
        )
    );

-- 3. RPC function to generate signed URL for visual asset (already exists in previous migration)
-- The get_visual_asset_signed_url function in migration 20261111000001_visual_asset_content_link.sql
-- returns the storage path for the application to generate signed URLs

-- Grant execute permissions on storage policies
-- Note: Storage policies are automatically enforced by Supabase
-- No additional grants needed for the bucket policies
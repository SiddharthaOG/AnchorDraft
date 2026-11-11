-- Retire unused legacy visual-asset RPC endpoints from all API roles.
-- The backend accesses assets through org-scoped table queries and Storage APIs.
-- Keeping these SECURITY DEFINER wrappers executable is unnecessary and creates
-- an exposed API surface that the backend does not use.
revoke all on function public.get_visual_asset(uuid) from public, anon, authenticated, service_role;
revoke all on function public.get_visual_asset_signed_url(uuid, integer) from public, anon, authenticated, service_role;
revoke all on function public.list_visual_assets(uuid, integer, integer) from public, anon, authenticated, service_role;
revoke all on function public.get_visual_assets_for_content(uuid) from public, anon, authenticated, service_role;

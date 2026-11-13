-- Preserve visual brand rules whenever an owner creates a new kit version.
-- Both clone_kit() and guideline-suggestion acceptance set source_kit_id.

begin;

create or replace function private.copy_visual_guidelines_from_source()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    if new.source_kit_id is null then
        return new;
    end if;

    if new.visual_guidelines is null or new.visual_guidelines = '{}'::jsonb then
        select coalesce(source.visual_guidelines, '{}'::jsonb)
          into new.visual_guidelines
          from public.brand_kits source
         where source.id = new.source_kit_id
           and source.org_id = new.org_id;

        if not found then
            raise exception 'source_kit_not_found'
                using errcode = '23503';
        end if;
    end if;

    return new;
end;
$$;

revoke all on function private.copy_visual_guidelines_from_source()
    from public, anon, authenticated;

drop trigger if exists brand_kits_inherit_visual_guidelines
    on public.brand_kits;

create trigger brand_kits_inherit_visual_guidelines
    before insert on public.brand_kits
    for each row
    execute function private.copy_visual_guidelines_from_source();

commit;

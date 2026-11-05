-- Migration: 20261104000007_triggers.sql
-- Description: Create BEFORE INSERT triggers to copy org_id from parent tables

-- 1. Trigger function for rules (copy org_id from brand_kits)
create or replace function private.set_rules_org_id()
returns trigger language plpgsql security definer set search_path = ''
as $$
begin
    select org_id into new.org_id
    from public.brand_kits
    where id = new.kit_id;
    if new.org_id is null then
        raise exception 'brand kit not found';
    end if;
    return new;
end $$;

create trigger trg_rules_set_org_id
    before insert on public.rules
    for each row execute function private.set_rules_org_id();

-- 2. Trigger function for approved_facts (copy org_id from brand_kits)
create or replace function private.set_approved_facts_org_id()
returns trigger language plpgsql security definer set search_path = ''
as $$
begin
    select org_id into new.org_id
    from public.brand_kits
    where id = new.kit_id;
    if new.org_id is null then
        raise exception 'brand kit not found';
    end if;
    return new;
end $$;

create trigger trg_approved_facts_set_org_id
    before insert on public.approved_facts
    for each row execute function private.set_approved_facts_org_id();

-- 3. Trigger function for revisions (copy org_id from contents)
create or replace function private.set_revisions_org_id()
returns trigger language plpgsql security definer set search_path = ''
as $$
begin
    select org_id into new.org_id
    from public.contents
    where id = new.content_id;
    if new.org_id is null then
        raise exception 'content not found';
    end if;
    return new;
end $$;

create trigger trg_revisions_set_org_id
    before insert on public.revisions
    for each row execute function private.set_revisions_org_id();

-- 4. Trigger function for findings (copy org_id from reviews)
create or replace function private.set_findings_org_id()
returns trigger language plpgsql security definer set search_path = ''
as $$
begin
    select org_id into new.org_id
    from public.reviews
    where id = new.review_id;
    if new.org_id is null then
        raise exception 'review not found';
    end if;
    return new;
end $$;

create trigger trg_findings_set_org_id
    before insert on public.findings
    for each row execute function private.set_findings_org_id();

-- Create private schema if not exists (for helper functions)
create schema if not exists private;
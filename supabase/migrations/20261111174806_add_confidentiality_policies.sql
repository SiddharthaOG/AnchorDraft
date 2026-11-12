-- Organization-scoped confidentiality settings for outbound AI review payloads.
-- The service-role review engine reads this table; direct writes are intentionally unavailable.

begin;

create table public.confidentiality_policies (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null unique references public.organizations(id) on delete cascade,
    enabled boolean not null default true,
    custom_terms text[] not null default '{}'::text[],
    redact_emails boolean not null default true,
    redact_phones boolean not null default true,
    redact_api_keys boolean not null default true,
    redact_jwts boolean not null default true,
    redact_credit_cards boolean not null default true,
    version integer not null default 1 check (version > 0),
    updated_by uuid null references auth.users(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint confidentiality_custom_terms_no_empty
        check (array_position(custom_terms, '') is null)
);

create index idx_confidentiality_policies_org
    on public.confidentiality_policies (org_id);

alter table public.confidentiality_policies enable row level security;

-- Policy contents can reveal which terms are protected. Only managers and owners
-- may inspect them. The backend uses the service role and enforces org binding.
create policy confidentiality_policies_select_managers
    on public.confidentiality_policies
    for select to authenticated
    using (
        private.has_role(org_id, 'manager')
        or private.has_role(org_id, 'owner')
    );

revoke all on public.confidentiality_policies from anon, authenticated;
grant select on public.confidentiality_policies to authenticated;

create or replace function private.bump_confidentiality_policy_version()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    new.version := old.version + 1;
    new.updated_at := now();
    return new;
end;
$$;

revoke all on function private.bump_confidentiality_policy_version() from public, anon, authenticated;

create trigger confidentiality_policy_version_before_update
    before update on public.confidentiality_policies
    for each row
    execute function private.bump_confidentiality_policy_version();

commit;

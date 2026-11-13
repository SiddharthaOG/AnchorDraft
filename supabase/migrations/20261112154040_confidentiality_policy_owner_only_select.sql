-- Restrict direct confidentiality policy reads to organization owners.
-- The review engine and owner API use the server-side service-role client;
-- managers and other authenticated roles must not read protected term values.

begin;

drop policy if exists confidentiality_policies_select_managers
    on public.confidentiality_policies;

create policy confidentiality_policies_select_owners
    on public.confidentiality_policies
    for select to authenticated
    using (private.has_role(org_id, 'owner'));

commit;

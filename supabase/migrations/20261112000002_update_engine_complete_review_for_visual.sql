-- Migration: 20261112000002_update_engine_complete_review_for_visual.sql
-- Description: Update engine_complete_review to handle visual findings with asset_id and region

-- Update engine_complete_review to handle visual findings with asset_id and region
-- Preserves all original behavior including claim-token fencing, atomic persistence, recovery behavior

create or replace function public.engine_complete_review(
    _review_id uuid,
    _status public.review_status,
    _llm_status public.llm_status,
    _warnings jsonb,
    _llm_findings_raw int,
    _llm_findings_dropped int,
    _validator_stats jsonb,
    _model text,
    _prompt_version text,
    _findings jsonb,
    _claim_token uuid
)
returns void
language plpgsql security definer set search_path = ''
as $$
declare
    _review public.reviews%rowtype;
    _finding jsonb;
    _rule_id uuid;
    _fact_id uuid;
    _asset_id uuid;
    _region jsonb;
begin
    -- 1. Get review row (locked for update) - preserves claim-token fencing
    select * into _review
    from public.reviews
    where id = _review_id
    for update;

    if not found then
        raise exception 'not_found';
    end if;

    -- 2. Validate claim_token (MANDATORY - reject NULL and mismatched tokens)
    if _claim_token is null
       or _review.claim_token is null
       or _review.claim_token <> _claim_token then
        raise exception 'claim_token_mismatch';
    end if;

    -- 2. Update review row
    update public.reviews
    set status = _status,
        llm_status = _llm_status,
        warnings = _warnings,
        llm_findings_raw = _llm_findings_raw,
        llm_findings_dropped = _llm_findings_dropped,
        validator_stats = _validator_stats,
        model = _model,
        prompt_version = _prompt_version,
        finished_at = now(),
        claim_token = null,
        claimed_at = null
    where id = _review_id;

    -- 3. If status is done, insert findings
    if _status = 'done' then
        for _finding in select * from jsonb_array_elements(_findings)
        loop
            -- Resolve rule_id or fact_id from ref_key
            _rule_id := null;
            _fact_id := null;
            _asset_id := null;
            _region := null;

            if (_finding->>'source') = 'deterministic' then
                select id into _rule_id
                from public.rules
                where kit_id = _review.kit_id and rule_key = _finding->>'ref_key';
            else
                -- Check both rules and facts for llm findings
                select id into _rule_id
                from public.rules
                where kit_id = _review.kit_id and rule_key = _finding->>'ref_key';

                if _rule_id is null then
                    select id into _fact_id
                    from public.approved_facts
                    where kit_id = _review.kit_id and fact_key = _finding->>'ref_key';
                end if;
            end if;

            if _rule_id is null and _fact_id is null then
                -- This should not happen if validator worked, but guard anyway
                raise exception 'unknown_ref';
            end if;

            -- Extract visual evidence if present
            _asset_id := nullif(_finding->>'asset_id', '')::uuid;
            _region := _finding->>'region';

            -- Validate visual evidence if present
            if _asset_id is not null then
                -- Verify asset belongs to the same org as the review
                if not exists (
                    select 1 from public.visual_assets
                    where id = _asset_id and org_id = _review.org_id
                ) then
                    raise exception 'visual_asset_not_in_org';
                end if;

                -- Validate region format if present
                if _region is not null then
                    if not (_region ? 'x' and _region ? 'y' and _region ? 'w' and _region ? 'h') then
                        raise exception 'invalid_region_format';
                    end if;

                    -- Validate region values are in [0, 1] range
                    if (_region->>'x')::numeric < 0 or (_region->>'x')::numeric > 1
                       or (_region->>'y')::numeric < 0 or (_region->>'y')::numeric > 1
                       or (_region->>'w')::numeric <= 0 or (_region->>'w')::numeric > 1
                       or (_region->>'h')::numeric <= 0 or (_region->>'h')::numeric > 1
                       or ( (_region->>'x')::numeric + (_region->>'w')::numeric ) > 1
                       or ( (_region->>'y')::numeric + (_region->>'h')::numeric ) > 1 then
                        raise exception 'invalid_region_bounds';
                    end if;
                end if;
            end if;

            if _rule_id is null and _fact_id is null then
                -- This should not happen if validator worked, but guard anyway
                raise exception 'unknown_ref';
            end if;

            insert into public.findings (
                org_id, review_id, source, rule_id, fact_id, ref_key,
                category, severity, quote, start_offset, end_offset,
                explanation, suggestion, confidence, needs_human, needs_reviewer,
                asset_id, region
            ) values (
                _review.org_id,
                _review_id,
                (_finding->>'source')::public.finding_source,
                _rule_id,
                _fact_id,
                _finding->>'ref_key',
                (_finding->>'category')::public.rule_category,
                (_finding->>'severity')::public.severity,
                _finding->>'quote',
                case when _finding->>'start_offset' is not null then (_finding->>'start_offset')::int end,
                case when _finding->>'end_offset' is not null then (_finding->>'end_offset')::int end,
                _finding->>'explanation',
                nullif(_finding->>'suggestion', ''),
                case when _finding->>'confidence' is not null then (_finding->>'confidence')::numeric(3,2) end,
                coalesce((_finding->>'needs_human')::boolean, false),
                coalesce((_finding->>'needs_reviewer')::boolean, false),
                _asset_id,
                _region
            );
        end loop;
    end if;

    -- 4. Audit log (actor_id = null for service-role calls)
    insert into public.audit_log (org_id, actor_id, action, entity_type, entity_id, detail)
    values (_review.org_id, null, 'review.completed', 'review', _review_id, jsonb_build_object('status', _status, 'llm_status', _llm_status));
end $$;

-- Service-only function: engine_fail_review (preserve original behavior with claim_token validation)
drop function if exists public.engine_fail_review(uuid, text);

create or replace function public.engine_fail_review(
    _review_id uuid,
    _error text,
    _claim_token uuid
)
returns void
language plpgsql security definer set search_path = ''
as $$
declare
    _review public.reviews%rowtype;
begin
    select * into _review
    from public.reviews
    where id = _review_id
    for update;

    if not found then
        raise exception 'not_found';
    end if;

    -- Validate claim_token (MANDATORY - reject NULL and mismatched tokens)
    if _claim_token is null
       or _review.claim_token is null
       or _review.claim_token <> _claim_token then
        raise exception 'claim_token_mismatch';
    end if;

    update public.reviews
    set status = 'failed',
        error = _error,
        finished_at = now(),
        claim_token = null,
        claimed_at = null
    where id = _review_id;

    insert into public.audit_log (org_id, actor_id, action, entity_type, entity_id, detail)
    values (_review.org_id, null, 'review.failed', 'review', _review_id, jsonb_build_object('error', _error));
end $$;

-- Revoke from public/anon/authenticated, grant only to service_role
revoke all on function public.engine_complete_review(uuid,public.review_status,public.llm_status,jsonb,int,int,jsonb,text,text,jsonb,uuid) from public, anon, authenticated;
revoke all on function public.engine_fail_review(uuid,text,uuid) from public, anon, authenticated;

-- Grant execute to service_role (the review service uses this role)
grant execute on function public.engine_complete_review(uuid,public.review_status,public.llm_status,jsonb,int,int,jsonb,text,text,jsonb,uuid) to service_role;
grant execute on function public.engine_fail_review(uuid,text,uuid) to service_role;
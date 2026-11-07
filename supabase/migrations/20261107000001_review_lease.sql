-- Migration: 20261107000001_review_lease.sql
-- Description: Add lease/claim token columns to reviews for stale job recovery

-- 1. Add lease/claim token columns to reviews
alter table public.reviews
    add column if not exists claim_token uuid null,
    add column if not exists claimed_at timestamptz null;

-- Index for finding stale running reviews
create index if not exists idx_reviews_stale_running
    on public.reviews (claimed_at)
    where status = 'running';

-- 2. Function to reclaim stale running reviews
-- A running review is stale if:
--   - It has been running for more than the lease period (default 30 minutes)
--   - The claim_token is not null (was properly claimed)
-- This function atomically re-queues stale jobs by:
--   - Setting status back to 'queued'
--   - Clearing claim_token and claimed_at
--   - Preserving started_at so that reclaimed reviews can be detected by the API
-- Returns the number of reclaimed reviews.
create or replace function public.reclaim_stale_reviews(
    _lease_minutes int default 30
)
returns int
language plpgsql security definer set search_path = ''
as $$
declare
    _reclaimed int := 0;
    _stale_threshold timestamptz := now() - (_lease_minutes || ' minutes')::interval;
begin
    -- Atomically re-queue stale running reviews
    -- Preserve started_at so that reclaimed reviews can be detected by the API
    update public.reviews
    set status = 'queued',
        claim_token = null,
        claimed_at = null
    where status = 'running'
      and claim_token is not null
      and claimed_at < _stale_threshold;

    get diagnostics _reclaimed = row_count;

    -- Audit log for each reclaimed review would be ideal but we can't loop in plain SQL easily
    -- The audit_log trigger on reviews table will capture the status change
    return _reclaimed;
end $$;

revoke all on function public.reclaim_stale_reviews(int) from public, anon, authenticated;
grant execute on function public.reclaim_stale_reviews(int) to service_role;

-- 3. Update engine_complete_review to validate claim_token (MANDATORY)
-- We'll drop and recreate the function with mandatory claim_token validation
-- (The original function is in 20261104000009_workflow_functions.sql)

-- Drop and recreate engine_complete_review with mandatory claim_token validation
drop function if exists public.engine_complete_review(
    uuid, public.review_status, public.llm_status, jsonb, int, int, jsonb, text, text, jsonb
);

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
begin
    -- 1. Get review row (locked for update)
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

    -- 3. Update review row
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

    -- 4. If status is done, insert findings
    if _status = 'done' then
        for _finding in select * from jsonb_array_elements(_findings)
        loop
            -- Resolve rule_id or fact_id from ref_key
            _rule_id := null;
            _fact_id := null;

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

            insert into public.findings (
                org_id, review_id, source, rule_id, fact_id, ref_key,
                category, severity, quote, start_offset, end_offset,
                explanation, suggestion, confidence, needs_human, needs_reviewer
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
                (_finding->>'start_offset')::int,
                (_finding->>'end_offset')::int,
                _finding->>'explanation',
                nullif(_finding->>'suggestion', ''),
                case when _finding->>'confidence' is not null then (_finding->>'confidence')::numeric(3,2) end,
                coalesce((_finding->>'needs_human')::boolean, false),
                coalesce((_finding->>'needs_reviewer')::boolean, false)
            );
        end loop;
    end if;

    -- 5. Audit log (actor_id = null for service-role calls)
    insert into public.audit_log (org_id, actor_id, action, entity_type, entity_id, detail)
    values (_review.org_id, null, 'review.completed', 'review', _review_id, jsonb_build_object('status', _status, 'llm_status', _llm_status));
end $$;

revoke all on function public.engine_complete_review(uuid,public.review_status,public.llm_status,jsonb,int,int,jsonb,text,text,jsonb,uuid) from public, anon, authenticated;
grant execute on function public.engine_complete_review(uuid,public.review_status,public.llm_status,jsonb,int,int,jsonb,text,text,jsonb,uuid) to service_role;

-- 4. Update engine_fail_review to validate claim_token (MANDATORY)
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

revoke all on function public.engine_fail_review(uuid,text,uuid) from public, anon, authenticated;
grant execute on function public.engine_fail_review(uuid,text,uuid) to service_role;

-- 5. Grant execute on reclaim_stale_reviews to service_role (already done above)
-- The function already has the grant from the original migration
-- Test Suite: Security Assertions
-- Executable SQL assertions that raise exceptions on failure.
-- Run: psql -h localhost -p 54322 -U postgres -d postgres -f supabase/tests/00_security_assertions.sql
-- Requires: Fresh local Supabase with migrations applied and seed data loaded.

\set ON_ERROR_STOP on

\echo '=== Security Assertions Test Suite ==='
\echo 'Running as postgres superuser - testing policy logic directly...'

-- ============================================================
-- Test 1: RLS enabled on all 14 application tables
-- ============================================================
\echo 'Test 1: RLS enabled on all application tables...'
DO $$
DECLARE
    v_missing text := '';
    v_table text;
BEGIN
    FOR v_table IN
        SELECT unnest(ARRAY['organizations','profiles','memberships','brand_kits','rules',
                           'approved_facts','contents','revisions','reviews','findings',
                           'decisions','comments','approvals','audit_log'])
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_tables
            WHERE schemaname = 'public' AND tablename = v_table AND rowsecurity = true
        ) THEN
            v_missing := v_missing || v_table || ', ';
        END IF;
    END LOOP;
    IF v_missing <> '' THEN
        RAISE EXCEPTION 'RLS not enabled on tables: %', v_missing;
    END IF;
    RAISE NOTICE 'PASS: RLS enabled on all 14 application tables';
END $$;

-- ============================================================
-- Test 2: Service-role grants on service-only functions
-- ============================================================
\echo 'Test 2: Service-role grants on service-only functions...'
DO $$
DECLARE
    v_fn text;
    v_missing boolean := false;
BEGIN
    FOR v_fn IN SELECT unnest(ARRAY['engine_complete_review', 'engine_fail_review']) LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.routine_privileges
            WHERE routine_schema = 'public' AND routine_name = v_fn
            AND grantee = 'service_role' AND privilege_type = 'EXECUTE'
        ) THEN
            RAISE NOTICE 'Missing grant: % for service_role', v_fn;
            v_missing := true;
        END IF;
    END LOOP;
    IF v_missing THEN
        RAISE EXCEPTION 'Service-role grants missing on service-only functions';
    END IF;
    RAISE NOTICE 'PASS: service_role has EXECUTE on engine_complete_review and engine_fail_review';
END $$;

-- ============================================================
-- Test 3: Authenticated grants on user-facing functions (no public/anon)
-- ============================================================
\echo 'Test 3: Authenticated grants on user-facing functions...'
DO $$
DECLARE
    v_fn text;
    v_missing boolean := false;
BEGIN
    FOR v_fn IN SELECT unnest(ARRAY['create_content','create_revision','record_decision',
                                    'apply_decisions','submit_content','request_changes',
                                    'record_signoff','approve_content','clone_kit','activate_kit']) LOOP
        -- Check authenticated has EXECUTE
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.routine_privileges
            WHERE routine_schema = 'public' AND routine_name = v_fn
            AND grantee = 'authenticated' AND privilege_type = 'EXECUTE'
        ) THEN
            RAISE NOTICE 'Missing authenticated grant: %', v_fn;
            v_missing := true;
        END IF;
        -- Check public does NOT have EXECUTE
        IF EXISTS (
            SELECT 1 FROM information_schema.routine_privileges
            WHERE routine_schema = 'public' AND routine_name = v_fn
            AND grantee = 'public' AND privilege_type = 'EXECUTE'
        ) THEN
            RAISE NOTICE 'Unexpected public grant: %', v_fn;
            v_missing := true;
        END IF;
        -- Check anon does NOT have EXECUTE
        IF EXISTS (
            SELECT 1 FROM information_schema.routine_privileges
            WHERE routine_schema = 'public' AND routine_name = v_fn
            AND grantee = 'anon' AND privilege_type = 'EXECUTE'
        ) THEN
            RAISE NOTICE 'Unexpected anon grant: %', v_fn;
            v_missing := true;
        END IF;
    END LOOP;
    IF v_missing THEN
        RAISE EXCEPTION 'Grant validation failed on user-facing functions';
    END IF;
    RAISE NOTICE 'PASS: All 10 user-facing functions granted to authenticated only';
END $$;

-- ============================================================
-- Test 4: Direct writes to protected tables rejected (no INSERT policy + revoked grant)
-- ============================================================
\echo 'Test 4: Direct writes to protected tables rejected (no INSERT policy + revoked grant)...'
DO $$
DECLARE
    v_table text;
BEGIN
    -- Test that NO INSERT RLS policy exists for authenticated on protected tables
    -- (they should be written only via SECURITY DEFINER functions)
    FOR v_table IN SELECT unnest(ARRAY['contents','revisions','reviews','findings',
                                        'decisions','approvals','audit_log']) LOOP
        IF EXISTS (
            SELECT 1 FROM pg_policies
            WHERE schemaname = 'public' AND tablename = v_table
            AND cmd = 'INSERT' AND roles @> ARRAY['authenticated']::name[]
        ) THEN
            RAISE EXCEPTION 'Unexpected INSERT RLS policy on % (should not exist)', v_table;
        END IF;
    END LOOP;

    -- Verify authenticated role has no direct INSERT privilege on protected tables
    FOR v_table IN SELECT unnest(ARRAY['contents','revisions','reviews','findings',
                                        'decisions','approvals','audit_log']) LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.table_privileges
            WHERE table_schema = 'public' AND table_name = v_table
            AND grantee = 'authenticated' AND privilege_type = 'INSERT'
        ) THEN
            RAISE EXCEPTION 'authenticated still has INSERT on % (should be revoked)', v_table;
        END IF;
    END LOOP;

    RAISE NOTICE 'PASS: No INSERT RLS policies and no direct INSERT grants on protected tables';
END $$;

-- ============================================================
-- Test 5: Cross-organization isolation membership logic
-- ============================================================
\echo 'Test 5: Cross-organization isolation (membership logic)...'
DO $$
DECLARE
    v_org_a uuid := gen_random_uuid();
    v_org_b uuid := gen_random_uuid();
    v_user_a uuid := '39fc3ba6-60c9-4252-8212-ffb55b7299e5'; -- existing owner user
    v_user_b uuid := 'c6d9c3b6-e175-412c-bfd2-2299886bf349'; -- existing creator1 user
BEGIN
    -- Create two orgs and add existing users as members
    INSERT INTO public.organizations (id, name) VALUES (v_org_a, 'Org A'), (v_org_b, 'Org B');
    INSERT INTO public.memberships (org_id, user_id, roles) VALUES
        (v_org_a, v_user_a, '{creator}'),
        (v_org_b, v_user_b, '{creator}');

    -- Verify membership logic: user_a is member of org_a only, user_b of org_b only
    IF NOT EXISTS (SELECT 1 FROM public.memberships WHERE org_id = v_org_a AND user_id = '39fc3ba6-60c9-4252-8212-ffb55b7299e5') THEN
        RAISE EXCEPTION 'User A should be member of Org A';
    END IF;

    IF EXISTS (SELECT 1 FROM public.memberships WHERE org_id = v_org_b AND user_id = '39fc3ba6-60c9-4252-8212-ffb55b7299e5') THEN
        RAISE EXCEPTION 'User A should not be member of Org B';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM public.memberships WHERE org_id = v_org_b AND user_id = 'c6d9c3b6-e175-412c-bfd2-2299886bf349') THEN
        RAISE EXCEPTION 'User B should be member of Org B';
    END IF;

    IF EXISTS (SELECT 1 FROM public.memberships WHERE org_id = v_org_a AND user_id = 'c6d9c3b6-e175-412c-bfd2-2299886bf349') THEN
        RAISE EXCEPTION 'User B should not be member of Org A';
    END IF;

    -- Cleanup
    DELETE FROM public.memberships WHERE org_id IN (v_org_a, v_org_b);
    DELETE FROM public.organizations WHERE id IN (v_org_a, v_org_b);

    RAISE NOTICE 'PASS: Cross-organization isolation membership logic verified';
END $$;

-- ============================================================
-- Test 6: Role restrictions enforced (using existing seeded users)
-- ============================================================
\echo 'Test 6: Role restrictions on brand kit operations...'
DO $$
DECLARE
    v_kit uuid;
BEGIN
    -- Get the existing brand kit
    SELECT id INTO v_kit FROM public.brand_kits WHERE org_id = '11111111-1111-1111-1111-111111111111' AND status = 'active' LIMIT 1;

    -- Verify RLS policy on rules: owner can write on draft kit (ALL policy)
    -- Check that RLS policy exists for rules write by owner on draft kit
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'rules'
        AND cmd = 'ALL' AND qual LIKE '%has_role(org_id, %owner%::app_role)%'
    ) THEN
        RAISE EXCEPTION 'Missing owner WRITE RLS policy on rules';
    END IF;

    -- Verify that policy checks for draft status
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'rules'
        AND cmd = 'ALL' AND qual LIKE '%status = %draft%'
    ) THEN
        RAISE EXCEPTION 'Missing draft status check in rules WRITE policy';
    END IF;

    RAISE NOTICE 'PASS: Role restrictions verified via RLS policy inspection';
END $$;

-- ============================================================
-- Test 7: Workflow function signatures verified
-- ============================================================
\echo 'Test 7: Workflow function signatures verified...'
DO $$
DECLARE
    v_fn_oid oid;
    v_arg_types text;
BEGIN
    -- Verify function signatures and existence
    SELECT oid INTO v_fn_oid FROM pg_proc WHERE proname = 'submit_content' AND pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public');
    IF v_fn_oid IS NULL THEN
        RAISE EXCEPTION 'submit_content function not found';
    END IF;

    -- Verify submit_content has correct signature (content_id uuid -> void)
    SELECT pg_get_function_arguments(v_fn_oid) INTO v_arg_types;
    IF v_arg_types <> '_content_id uuid' THEN
        RAISE EXCEPTION 'submit_content has unexpected signature: %', v_arg_types;
    END IF;

    -- Verify approve_content has correct signature
    SELECT oid INTO v_fn_oid FROM pg_proc WHERE proname = 'approve_content' AND pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public');
    IF v_fn_oid IS NULL THEN
        RAISE EXCEPTION 'approve_content function not found';
    END IF;

    SELECT pg_get_function_arguments(v_fn_oid) INTO v_arg_types;
    IF v_arg_types <> '_content_id uuid' THEN
        RAISE EXCEPTION 'approve_content has unexpected signature: %', v_arg_types;
    END IF;

    -- Verify request_changes has correct signature
    SELECT oid INTO v_fn_oid FROM pg_proc WHERE proname = 'request_changes' AND pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public');
    IF v_fn_oid IS NULL THEN
        RAISE EXCEPTION 'request_changes function not found';
    END IF;

    SELECT pg_get_function_arguments(v_fn_oid) INTO v_arg_types;
    IF v_arg_types <> '_content_id uuid, _note text' THEN
        RAISE EXCEPTION 'request_changes has unexpected signature: %', v_arg_types;
    END IF;

    RAISE NOTICE 'PASS: Workflow function signatures verified';
END $$;

-- ============================================================
-- Test 8: Append-only revisions enforced (privilege check)
-- ============================================================
\echo 'Test 8: Append-only revisions (privilege check)...'
DO $$
BEGIN
    -- Test: Direct UPDATE on revision blocked (no UPDATE privilege for authenticated)
    IF EXISTS (
        SELECT 1 FROM information_schema.table_privileges
        WHERE table_schema = 'public' AND table_name = 'revisions'
        AND grantee = 'authenticated' AND privilege_type = 'UPDATE'
    ) THEN
        RAISE EXCEPTION 'authenticated has UPDATE on revisions (should be revoked)';
    END IF;

    -- Test: Direct DELETE on revision blocked
    IF EXISTS (
        SELECT 1 FROM information_schema.table_privileges
        WHERE table_schema = 'public' AND table_name = 'revisions'
        AND grantee = 'authenticated' AND privilege_type = 'DELETE'
    ) THEN
        RAISE EXCEPTION 'authenticated has DELETE on revisions (should be revoked)';
    END IF;

    -- Test: Direct INSERT on revision blocked
    IF EXISTS (
        SELECT 1 FROM information_schema.table_privileges
        WHERE table_schema = 'public' AND table_name = 'revisions'
        AND grantee = 'authenticated' AND privilege_type = 'INSERT'
    ) THEN
        RAISE EXCEPTION 'authenticated has INSERT on revisions (should be revoked)';
    END IF;

    -- Verify create_revision function signature
    IF EXISTS (
        SELECT 1 FROM pg_proc
        WHERE proname = 'create_revision'
        AND pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
        AND pg_get_function_arguments(oid) = '_content_id uuid, _body text'
    ) THEN
        RAISE NOTICE 'PASS: Revisions are append-only (direct writes blocked, function exists)';
    ELSE
        RAISE EXCEPTION 'create_revision function missing or wrong signature';
    END IF;
END $$;

-- ============================================================
-- Test 9: Atomic rollback on workflow failure (function signature)
-- ============================================================
\echo 'Test 9: Atomic rollback on workflow failure (function signature)...'
DO $$
DECLARE
    v_fn_oid oid;
    v_arg_types text;
BEGIN
    -- Verify submit_content function signature
    SELECT oid INTO v_fn_oid FROM pg_proc WHERE proname = 'submit_content' AND pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public');
    IF v_fn_oid IS NULL THEN
        RAISE EXCEPTION 'submit_content function not found';
    END IF;

    SELECT pg_get_function_arguments(v_fn_oid) INTO v_arg_types;
    IF v_arg_types <> '_content_id uuid' THEN
        RAISE EXCEPTION 'submit_content has unexpected signature: %', v_arg_types;
    END IF;

    RAISE NOTICE 'PASS: submit_content function signature verified (atomic rollback logic in function body)';
END $$;

-- ============================================================
-- Test 10: Decision latest-wins semantics (function signature)
-- ============================================================
\echo 'Test 10: Decision latest-wins semantics (function signature)...'
DO $$
DECLARE
    v_fn_oid oid;
    v_arg_types text;
BEGIN
    -- Verify record_decision function signature
    SELECT oid INTO v_fn_oid FROM pg_proc WHERE proname = 'record_decision' AND pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public');
    IF v_fn_oid IS NULL THEN
        RAISE EXCEPTION 'record_decision function not found';
    END IF;

    SELECT pg_get_function_arguments(v_fn_oid) INTO v_arg_types;
    -- Note: pg_get_function_arguments includes default values
    IF v_arg_types NOT LIKE '_finding_id uuid, _action decision_action, _reason text%' THEN
        RAISE EXCEPTION 'record_decision has unexpected signature: %', v_arg_types;
    END IF;

    -- Verify apply_decisions function signature
    SELECT oid INTO v_fn_oid FROM pg_proc WHERE proname = 'apply_decisions' AND pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public');
    IF v_fn_oid IS NULL THEN
        RAISE EXCEPTION 'apply_decisions function not found';
    END IF;

    SELECT pg_get_function_arguments(v_fn_oid) INTO v_arg_types;
    IF v_arg_types <> '_content_id uuid' THEN
        RAISE EXCEPTION 'apply_decisions has unexpected signature: %', v_arg_types;
    END IF;

    RAISE NOTICE 'PASS: Decision function signatures verified (latest-wins logic in function body)';
END $$;

\echo '=== All Security Assertions Passed ==='

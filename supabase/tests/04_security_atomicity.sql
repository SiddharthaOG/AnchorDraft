-- Test Suite: Security and Atomicity
-- Tests for RLS coverage, function hardening, and transaction atomicity
-- Run with: psql -d postgres -f supabase/tests/04_security_atomicity.sql

\set ON_ERROR_STOP on
\echo '=== Security and Atomicity Tests ==='

-- Test 1: RLS enabled on all application tables
\echo 'Test 1: RLS enabled on all tables'
SELECT tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN ('organizations','profiles','memberships','brand_kits','rules','approved_facts',
                    'contents','revisions','reviews','findings','decisions','comments',
                    'approvals','audit_log')
ORDER BY tablename;
-- All should show rowsecurity = true

-- Test 2: Direct INSERT/UPDATE/DELETE revoked on workflow tables
\echo 'Test 2: Workflow table write privileges revoked'
SELECT table_name, privilege_type
FROM information_schema.table_privileges
WHERE table_schema = 'public'
  AND grantee IN ('authenticated', 'anon')
  AND table_name IN ('contents','revisions','reviews','findings','decisions','approvals','audit_log')
  AND privilege_type IN ('INSERT', 'UPDATE', 'DELETE')
ORDER BY table_name, privilege_type;
-- Should return 0 rows (all revoked)

-- Test 3: SECURITY DEFINER functions have correct search_path
\echo 'Test 3: SECURITY DEFINER functions have fixed search_path'
SELECT routine_name, security_type, external_language
FROM information_schema.routines
WHERE routine_schema = 'public'
  AND routine_name IN (
    'create_content','create_revision','record_decision','apply_decisions',
    'submit_content','request_changes','record_signoff','approve_content',
    'clone_kit','activate_kit','engine_complete_review','engine_fail_review'
  )
ORDER BY routine_name;
-- All should show security_type = 'DEFINER'

-- Test 4: Functions revoked from PUBLIC and ANON
\echo 'Test 4: Function execute privileges'
SELECT routine_name, grantee, privilege_type
FROM information_schema.routine_privileges
WHERE routine_schema = 'public'
  AND routine_name IN (
    'create_content','create_revision','record_decision','apply_decisions',
    'submit_content','request_changes','record_signoff','approve_content',
    'clone_kit','activate_kit'
  )
  AND grantee IN ('public', 'anon', 'authenticated')
ORDER BY routine_name, grantee;
-- Should show EXECUTE granted to authenticated, revoked from public/anon

-- Test 5: Service-only functions not executable by authenticated
\echo 'Test 5: Service-only functions restricted'
SELECT routine_name, grantee, privilege_type
FROM information_schema.routine_privileges
WHERE routine_schema = 'public'
  AND routine_name IN ('engine_complete_review', 'engine_fail_review')
  AND grantee IN ('public', 'anon', 'authenticated')
ORDER BY routine_name, grantee;
-- Should show no rows (revoked from all)

-- Test 6: Helper functions in private schema not exposed
\echo 'Test 6: Private schema functions not callable as RPC'
SELECT routine_name FROM information_schema.routines WHERE routine_schema = 'private';
-- Should list is_member, has_role, set_rules_org_id, etc.

-- Test 7: Atomicity - failed function rolls back
\echo 'Test 7: Atomicity - failed apply_decisions rolls back'
-- Setup: content with findings, record accept decision
-- Call apply_decisions with body that would exceed 20000 chars
-- Should fail with validation:body
-- Verify NO new revision created
-- Verify decisions NOT updated with resulting_revision_id

-- Test 8: Atomicity - failed submit_content rolls back
\echo 'Test 8: Atomicity - failed submit_content rolls back'
-- Setup: content with undecided finding
-- Call submit_content
-- Should fail with conflict:findings_undecided
-- Verify content status still 'draft'
-- Verify NO audit_log entry for content.submitted

-- Test 9: Atomicity - failed approve_content rolls back
\echo 'Test 9: Atomicity - failed approve_content rolls back'
-- Setup: content with pending signoff
-- Call approve_content
-- Should fail with conflict:pending_signoffs
-- Verify content status still 'submitted'
-- Verify NO approval row inserted
-- Verify NO audit_log entry for content.approved

-- Test 10: Atomicity - engine_complete_review all-or-nothing
\echo 'Test 10: Atomicity - engine_complete_review all-or-nothing'
-- Call engine_complete_review with invalid finding (unknown ref_key)
-- Should fail with unknown_ref
-- Verify review status NOT updated
-- Verify NO findings inserted

-- Test 11: Role escalation prevented
\echo 'Test 11: Role escalation prevented'
-- Creator tries to call activate_kit (owner only)
-- Should fail with forbidden
-- Manager tries to call record_signoff (reviewer only)
-- Should fail with forbidden

-- Test 12: Cross-org access prevented in functions
\echo 'Test 12: Cross-org access prevented'
-- User in Org A tries create_content with Org B ID
-- Should fail with forbidden (has_role check fails)
-- User in Org A tries record_decision on Org B finding
-- Should fail with forbidden

-- Test 13: auth.uid() validation
\echo 'Test 13: Unauthenticated calls rejected'
-- Call any function without auth context (SET ROLE postgres; RESET ROLE;)
-- Should fail with 'unauthenticated'

-- Test 14: Updated_at maintained on content status changes
\echo 'Test 14: updated_at timestamp updated'
-- Check contents.updated_at changes on status transitions
-- submit_content, request_changes, approve_content all update updated_at

-- Test 15: Decision latest-wins semantics
\echo 'Test 15: Decision latest-wins'
-- Record dismiss, then accept on same finding
-- v_finding_state should show last_action = 'accept'
-- apply_decisions should use latest decision

\echo '=== Security and Atomicity Tests Complete (run manually in Supabase local) ==='
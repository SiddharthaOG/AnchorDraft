-- Test Suite: Organization Isolation and RLS
-- Run with: psql -d postgres -f supabase/tests/02_org_isolation_rls.sql
-- Requires: Two test users with memberships in different orgs

\set ON_ERROR_STOP on
\echo '=== Organization Isolation and RLS Tests ==='

-- This test file assumes you have set up test users and orgs
-- You can run these manually in a Supabase local dev environment

-- Test setup (run once):
-- CREATE USER test_user_a WITH PASSWORD 'test';
-- CREATE USER test_user_b WITH PASSWORD 'test';
-- INSERT INTO organizations (id, name) VALUES ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'Org A');
-- INSERT INTO organizations (id, name) VALUES ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'Org B');
-- INSERT INTO memberships (org_id, user_id, roles) VALUES ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'test_user_a', '{creator}');
-- INSERT INTO memberships (org_id, user_id, roles) VALUES ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'test_user_b', '{creator}');

-- The following tests verify RLS policies work correctly
-- They must be run as the test users (SET ROLE test_user_a; etc.)

-- Test 1: User A can only see Org A data
\echo 'Test 1: User A sees only Org A organizations'
-- SET ROLE test_user_a;
-- SELECT count(*) FROM organizations; -- Should return 1

-- Test 2: User B can only see Org B data
\echo 'Test 2: User B sees only Org B organizations'
-- SET ROLE test_user_b;
-- SELECT count(*) FROM organizations; -- Should return 1

-- Test 3: User A cannot insert into Org B
\echo 'Test 3: User A cannot insert brand kit in Org B'
-- SET ROLE test_user_a;
-- INSERT INTO brand_kits (org_id, version, name, status, created_by)
-- VALUES ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 1, 'Test', 'draft', current_user);
-- Should fail with RLS violation

-- Test 4: User A cannot update Org B data
\echo 'Test 4: User A cannot update Org B content'
-- SET ROLE test_user_a;
-- UPDATE contents SET title = 'Hacked' WHERE org_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
-- Should affect 0 rows

-- Test 5: Membership revocation removes access
\echo 'Test 5: Revoking membership removes access'
-- DELETE FROM memberships WHERE user_id = 'test_user_a' AND org_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
-- SET ROLE test_user_a;
-- SELECT count(*) FROM organizations; -- Should return 0

-- Test 6: Role restrictions on brand kit writes
\echo 'Test 6: Only owner can write draft kit rules'
-- SET ROLE test_user_a (creator only);
-- INSERT INTO rules (kit_id, rule_key, category, title, guideline_text, check_kind)
-- VALUES (<draft_kit_id>, 'TERM-99', 'terminology', 'Test', 'Test', 'deterministic');
-- Should fail (creator cannot write rules)

-- SET ROLE owner_user (owner role);
-- INSERT INTO rules ...; -- Should succeed

-- Test 7: Cannot write rules for active kit
\echo 'Test 7: Cannot write rules for active kit'
-- SET ROLE owner_user;
-- INSERT INTO rules (kit_id, rule_key, ...) VALUES (<active_kit_id>, 'TERM-99', ...);
-- Should fail (kit is not draft)

-- Test 8: Comments can only be inserted as self
\echo 'Test 8: Comments must be inserted as authenticated user'
-- SET ROLE test_user_a;
-- INSERT INTO comments (org_id, content_id, user_id, body)
-- VALUES ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', <content_id>, 'test_user_b', 'impersonation');
-- Should fail (user_id mismatch)

-- Test 9: Workflow tables reject direct inserts
\echo 'Test 9: Direct inserts on workflow tables rejected'
-- SET ROLE test_user_a;
-- INSERT INTO revisions (content_id, version, body, source, created_by) VALUES (...);
-- Should fail (INSERT revoked from authenticated)

-- Test 10: Audit log only readable by manager/owner
\echo 'Test 10: Audit log restricted to manager/owner'
-- SET ROLE test_user_a (creator);
-- SELECT count(*) FROM audit_log; -- Should return 0 (no access)
-- SET ROLE manager_user;
-- SELECT count(*) FROM audit_log; -- Should return rows

\echo '=== RLS Tests Complete (run manually in Supabase local) ==='
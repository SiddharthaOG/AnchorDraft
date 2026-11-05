-- Test Suite: Schema and Integrity
-- Run with: psql -d postgres -f supabase/tests/01_schema_integrity.sql
-- Or via Supabase CLI: supabase db reset && psql -d postgres -f supabase/tests/01_schema_integrity.sql

\set ON_ERROR_STOP on
\echo '=== Schema and Integrity Tests ==='

-- Test 1: All enums exist
\echo 'Test 1: Enums exist'
SELECT 'app_role' AS enum_name WHERE EXISTS (SELECT 1 FROM pg_type WHERE typname = 'app_role');
SELECT 'kit_status' AS enum_name WHERE EXISTS (SELECT 1 FROM pg_type WHERE typname = 'kit_status');
SELECT 'rule_category' AS enum_name WHERE EXISTS (SELECT 1 FROM pg_type WHERE typname = 'rule_category');
SELECT 'severity' AS enum_name WHERE EXISTS (SELECT 1 FROM pg_type WHERE typname = 'severity');
SELECT 'check_kind' AS enum_name WHERE EXISTS (SELECT 1 FROM pg_type WHERE typname = 'check_kind');
SELECT 'content_status' AS enum_name WHERE EXISTS (SELECT 1 FROM pg_type WHERE typname = 'content_status');
SELECT 'revision_source' AS enum_name WHERE EXISTS (SELECT 1 FROM pg_type WHERE typname = 'revision_source');
SELECT 'review_status' AS enum_name WHERE EXISTS (SELECT 1 FROM pg_type WHERE typname = 'review_status');
SELECT 'finding_source' AS enum_name WHERE EXISTS (SELECT 1 FROM pg_type WHERE typname = 'finding_source');
SELECT 'llm_status' AS enum_name WHERE EXISTS (SELECT 1 FROM pg_type WHERE typname = 'llm_status');
SELECT 'decision_action' AS enum_name WHERE EXISTS (SELECT 1 FROM pg_type WHERE typname = 'decision_action');
SELECT 'approval_action' AS enum_name WHERE EXISTS (SELECT 1 FROM pg_type WHERE typname = 'approval_action');

-- Test 2: All tables exist
\echo 'Test 2: Tables exist'
SELECT 'organizations' AS table_name WHERE EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'organizations');
SELECT 'profiles' AS table_name WHERE EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'profiles');
SELECT 'memberships' AS table_name WHERE EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'memberships');
SELECT 'brand_kits' AS table_name WHERE EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'brand_kits');
SELECT 'rules' AS table_name WHERE EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'rules');
SELECT 'approved_facts' AS table_name WHERE EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'approved_facts');
SELECT 'contents' AS table_name WHERE EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'contents');
SELECT 'revisions' AS table_name WHERE EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'revisions');
SELECT 'reviews' AS table_name WHERE EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'reviews');
SELECT 'findings' AS table_name WHERE EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'findings');
SELECT 'decisions' AS table_name WHERE EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'decisions');
SELECT 'comments' AS table_name WHERE EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'comments');
SELECT 'approvals' AS table_name WHERE EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'approvals');
SELECT 'audit_log' AS table_name WHERE EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'audit_log');

-- Test 3: Primary keys exist
\echo 'Test 3: Primary keys'
SELECT tc.table_name, kcu.column_name
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public'
ORDER BY tc.table_name;

-- Test 4: Foreign keys exist
\echo 'Test 4: Foreign keys'
SELECT tc.table_name, kcu.column_name, ccu.table_name AS referenced_table
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
ORDER BY tc.table_name;

-- Test 5: Check constraints
\echo 'Test 5: Check constraints'
SELECT tc.table_name, tc.constraint_name, cc.check_clause
FROM information_schema.table_constraints tc
JOIN information_schema.check_constraints cc ON tc.constraint_name = cc.constraint_name
WHERE tc.constraint_type = 'CHECK' AND tc.table_schema = 'public'
ORDER BY tc.table_name;

-- Test 6: Unique constraints
\echo 'Test 6: Unique constraints'
SELECT tc.table_name, tc.constraint_name, STRING_AGG(kcu.column_name, ', ') AS columns
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
WHERE tc.constraint_type = 'UNIQUE' AND tc.table_schema = 'public'
GROUP BY tc.table_name, tc.constraint_name
ORDER BY tc.table_name;

-- Test 7: Indexes exist
\echo 'Test 7: Key indexes'
SELECT indexname, tablename
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname IN (
    'idx_memberships_user_id',
    'idx_brand_kits_org_status',
    'idx_rules_kit_id',
    'idx_approved_facts_kit_id',
    'idx_contents_org_status_created',
    'idx_revisions_content_version',
    'idx_revisions_org_id',
    'idx_reviews_revision_created',
    'idx_reviews_org_status',
    'idx_findings_review_id',
    'idx_findings_org_ref_key',
    'idx_decisions_finding_created',
    'idx_comments_content_created',
    'idx_approvals_content_created',
    'idx_approvals_finding_id',
    'idx_audit_log_org_created'
  )
ORDER BY tablename, indexname;

-- Test 8: Views exist
\echo 'Test 8: Views'
SELECT table_name FROM information_schema.views WHERE table_schema = 'public' AND table_name IN ('v_latest_revision', 'v_finding_state', 'v_pending_signoffs', 'v_rule_stats');

-- Test 9: Trigger functions exist
\echo 'Test 9: Trigger functions'
SELECT routine_name FROM information_schema.routines WHERE routine_schema = 'private' AND routine_name IN ('set_rules_org_id', 'set_approved_facts_org_id', 'set_revisions_org_id', 'set_findings_org_id');

\echo '=== Schema Tests Complete ==='
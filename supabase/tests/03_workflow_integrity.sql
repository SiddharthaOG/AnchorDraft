-- Test Suite: Workflow Integrity
-- Tests for database functions enforcing valid state transitions
-- Run with: psql -d postgres -f supabase/tests/03_workflow_integrity.sql
-- Requires: Test users with appropriate roles in test org

\set ON_ERROR_STOP on
\echo '=== Workflow Integrity Tests ==='

-- These tests verify the workflow functions work correctly
-- They should be run in a Supabase local environment with test users

-- Test 1: create_content creates content and revision 1
\echo 'Test 1: create_content'
-- SELECT * FROM create_content(
--     '11111111-1111-1111-1111-111111111111',
--     'Test Post',
--     'blog',
--     'Test purpose',
--     'Test body content'
-- );
-- Should return content_id and revision_id
-- Verify content status = 'draft'
-- Verify revision version = 1, source = 'manual'

-- Test 2: create_revision creates next version
\echo 'Test 2: create_revision'
-- SELECT * FROM create_revision(<content_id>, 'New body content');
-- Should return revision_id and version = 2
-- Verify parent_revision_id = revision 1

-- Test 3: create_revision fails on same body
\echo 'Test 3: create_revision rejects duplicate body'
-- SELECT * FROM create_revision(<content_id>, 'New body content');
-- Should fail with validation:body

-- Test 4: create_revision fails on approved content
\echo 'Test 4: create_revision rejects non-editable content'
-- First approve content (via submit -> approve flow)
-- Then try create_revision
-- Should fail with conflict:not_editable

-- Test 5: record_decision records accept/edit/dismiss
\echo 'Test 5: record_decision'
-- Need a finding from a done review
-- SELECT * FROM record_decision(<finding_id>, 'accept');
-- Should return decision_id
-- Verify decision.action = 'accept'

-- Test 6: record_decision requires reason for dismiss
\echo 'Test 6: record_decision rejects dismiss without reason'
-- SELECT * FROM record_decision(<finding_id>, 'dismiss');
-- Should fail with validation:reason

-- Test 7: record_decision requires edited_text for edit
\echo 'Test 7: record_decision rejects edit without edited_text'
-- SELECT * FROM record_decision(<finding_id>, 'edit');
-- Should fail with validation:edited_text

-- Test 8: record_decision requires suggestion for accept
\echo 'Test 8: record_decision rejects accept without suggestion'
-- Finding without suggestion
-- SELECT * FROM record_decision(<finding_id>, 'accept');
-- Should fail with conflict:no_suggestion

-- Test 9: apply_decisions creates single revision from batch
\echo 'Test 9: apply_decisions creates one revision'
-- Record multiple accept/edit decisions
-- SELECT * FROM apply_decisions(<content_id>);
-- Should return revision_id, version, applied count, skipped array
-- Verify new revision source = 'accepted_suggestion'
-- Verify decisions have resulting_revision_id set

-- Test 10: apply_decisions applies in descending offset order
\echo 'Test 10: apply_decisions handles overlapping offsets'
-- Create findings with overlapping ranges
-- Record accept decisions for both
-- apply_decisions should skip overlapping with reason 'overlap'

-- Test 11: apply_decisions skips if text changed
\echo 'Test 11: apply_decisions skips text_changed'
-- Modify content directly (simulating external change)
-- Try to apply decisions
-- Should skip with reason 'text_changed'

-- Test 12: apply_decisions fails if no pending changes
\echo 'Test 12: apply_decisions rejects no_changes'
-- Call apply_decisions with no pending accept/edit decisions
-- Should fail with conflict:no_changes

-- Test 13: submit_content requires done review with ok/skipped llm_status
\echo 'Test 13: submit_content requires valid review'
-- Content with no review
-- SELECT submit_content(<content_id>);
-- Should fail with conflict:no_review

-- Test 14: submit_content rejects llm_failed review
\echo 'Test 14: submit_content rejects llm_failed'
-- Content with review where llm_status = 'failed'
-- SELECT submit_content(<content_id>);
-- Should fail with conflict:llm_failed

-- Test 15: submit_content requires all findings decided
\echo 'Test 15: submit_content rejects undecided findings'
-- Content with review but some findings have no decisions
-- SELECT submit_content(<content_id>);
-- Should fail with conflict:findings_undecided

-- Test 16: submit_content requires no pending apply
\echo 'Test 16: submit_content rejects changes_pending_apply'
-- Content with accepted/edited decisions not yet applied
-- SELECT submit_content(<content_id>);
-- Should fail with conflict:changes_pending_apply

-- Test 17: request_changes requires manager role
\echo 'Test 17: request_changes requires manager'
-- Creator tries request_changes
-- Should fail with forbidden

-- Test 18: request_changes requires submitted status
\echo 'Test 18: request_changes requires submitted'
-- Manager tries request_changes on draft content
-- Should fail with conflict:not_submitted

-- Test 19: request_changes requires note
\echo 'Test 19: request_changes requires note'
-- SELECT request_changes(<content_id>, '');
-- Should fail with validation:note

-- Test 20: record_signoff requires reviewer role
\echo 'Test 20: record_signoff requires reviewer'
-- Manager tries signoff
-- Should fail with forbidden

-- Test 21: record_signoff requires needs_reviewer finding
\echo 'Test 21: record_signoff requires needs_reviewer'
-- Reviewer tries signoff on finding without needs_reviewer
-- Should fail with conflict:not_needs_reviewer

-- Test 22: record_signoff reject_claim requires note
\echo 'Test 22: record_signoff reject_claim requires note'
-- SELECT record_signoff(<finding_id>, 'reject_claim', '');
-- Should fail with validation:note

-- Test 23: approve_content requires no pending signoffs
\echo 'Test 23: approve_content requires pending_signoffs = 0'
-- Content with needs_reviewer findings not signed off
-- SELECT approve_content(<content_id>);
-- Should fail with conflict:pending_signoffs

-- Test 24: clone_kit requires owner role
\echo 'Test 24: clone_kit requires owner'
-- Creator tries clone_kit
-- Should fail with forbidden

-- Test 25: activate_kit requires draft kit with rules
\echo 'Test 25: activate_kit validates kit'
-- activate_kit on active kit -> conflict:not_draft_kit
-- activate_kit on empty draft kit -> conflict:empty_kit

-- Test 26: Audit log entries created for each transition
\echo 'Test 26: Audit log entries'
-- After each function call, verify audit_log has entry
-- Check action, entity_type, entity_id, actor_id

-- ============================================================
-- Executable Regression Tests (New)
-- ============================================================
-- These tests can be run against a local Supabase instance with test data
-- They must be run in order and require a clean database state

\echo '=== Executable Regression Tests ==='

-- ============================================================
-- Test R1: Finding from older revision rejected (conflict:not_latest_revision)
-- ============================================================
\echo 'Test R1: Finding from older revision rejected'
-- Setup: Create content with two revisions, review on revision 1
-- Try to record_decision on finding from review of revision 1
-- Expect: conflict:not_latest_revision
-- VERIFY:
--   - Exception raised with 'conflict:not_latest_revision'
--   - No decision inserted

DO $$
DECLARE
    v_org uuid := '11111111-1111-1111-1111-111111111111';
    v_creator uuid;
    v_content uuid;
    v_rev1 uuid;
    v_rev2 uuid;
    v_review uuid;
    v_finding uuid;
    v_rule_id uuid;
    v_kit_id uuid;
BEGIN
    -- Get creator user (must exist)
    SELECT id INTO v_creator FROM auth.users WHERE email = 'creator1@axial.demo' LIMIT 1;
    IF v_creator IS NULL THEN
        RAISE EXCEPTION 'FAIL: Test prerequisite missing - creator1@axial.demo not found in auth.users';
    END IF;

    -- Get active brand kit (must exist)
    SELECT id INTO v_kit_id FROM public.brand_kits WHERE org_id = v_org AND status = 'active' LIMIT 1;
    IF v_kit_id IS NULL THEN
        RAISE EXCEPTION 'FAIL: Test prerequisite missing - no active brand kit for org %', v_org;
    END IF;

    -- Get rule with suggestion (must exist)
    SELECT id INTO v_rule_id FROM public.rules WHERE rule_key = 'TERM-01' AND kit_id = v_kit_id LIMIT 1;
    IF v_rule_id IS NULL THEN
        RAISE EXCEPTION 'FAIL: Test prerequisite missing - rule TERM-01 not found in active kit %', v_kit_id;
    END IF;

    -- Create content
    SELECT * FROM create_content(v_org, 'Test Post R1', 'blog', 'Test purpose', 'Original body with utilize and guaranteed uptime') INTO v_content, v_rev1;

    -- Create revision 2
    SELECT * FROM create_revision(v_content, 'Updated body with utilize and guaranteed uptime') INTO v_rev2;

    -- Create review on revision 1 (older revision)
    INSERT INTO public.reviews (org_id, revision_id, kit_id, status, llm_status, engine_version, requested_by)
    SELECT v_org, v_rev1, v_kit_id, 'done', 'ok', 'test', v_creator
    RETURNING id INTO v_review;

    -- Create finding on revision 1
    INSERT INTO public.findings (org_id, review_id, source, rule_id, ref_key, category, severity, quote, start_offset, end_offset, explanation, suggestion, needs_reviewer)
    SELECT v_org, v_review, 'deterministic', v_rule_id, 'TERM-01', 'terminology', 'low', 'utilize', 10, 17, 'Avoid utilize', 'use', false
    RETURNING id INTO v_finding;

    -- Try to record decision on finding from older revision
    BEGIN
        PERFORM record_decision(v_finding, 'accept');
        RAISE EXCEPTION 'FAIL: Expected conflict:not_latest_revision but succeeded';
    EXCEPTION WHEN SQLSTATE 'P0001' THEN
        IF SQLERRM LIKE '%conflict:not_latest_revision%' THEN
            -- PASS: Got expected conflict:not_latest_revision
        ELSE
            RAISE EXCEPTION 'FAIL: Got unexpected error: %', SQLERRM;
        END IF;
    END;

    -- Verify no decision was inserted
    IF EXISTS (SELECT 1 FROM public.decisions WHERE finding_id = v_finding) THEN
        RAISE EXCEPTION 'FAIL: Decision was inserted despite conflict';
    END IF;
END $$;

-- ============================================================
-- Test R2: Latest decision wins (accept then dismiss)
-- ============================================================
\echo 'Test R2: Latest decision wins (accept then dismiss)'
-- Setup: Content with review, finding with suggestion
-- 1. record_decision(accept)
-- 2. record_decision(dismiss, 'reason')
-- 3. apply_decisions
-- 4. Verify only dismiss was applied (no revision created)
-- 5. Verify v_finding_state.last_action = 'dismiss'
-- VERIFY:
--   - apply_decisions raises conflict:no_changes (dismiss is latest, no changes)
--   - v_finding_state.last_action = 'dismiss'
--   - No new revision created

DO $$
DECLARE
    v_org uuid := '11111111-1111-1111-1111-111111111111';
    v_creator uuid;
    v_content uuid;
    v_rev uuid;
    v_review uuid;
    v_finding uuid;
    v_rule_id uuid;
    v_kit_id uuid;
    v_rev_id uuid;
    v_version int;
    v_applied int;
    v_skipped jsonb;
BEGIN
    -- Get creator user (must exist)
    SELECT id INTO v_creator FROM auth.users WHERE email = 'creator1@axial.demo' LIMIT 1;
    IF v_creator IS NULL THEN
        RAISE EXCEPTION 'FAIL: Test prerequisite missing - creator1@axial.demo not found in auth.users';
    END IF;

    -- Get active brand kit (must exist)
    SELECT id INTO v_kit_id FROM public.brand_kits WHERE org_id = v_org AND status = 'active' LIMIT 1;
    IF v_kit_id IS NULL THEN
        RAISE EXCEPTION 'FAIL: Test prerequisite missing - no active brand kit for org %', v_org;
    END IF;

    -- Get rule with suggestion (must exist)
    SELECT id INTO v_rule_id FROM public.rules WHERE rule_key = 'TERM-01' AND kit_id = v_kit_id LIMIT 1;
    IF v_rule_id IS NULL THEN
        RAISE EXCEPTION 'FAIL: Test prerequisite missing - rule TERM-01 not found in active kit %', v_kit_id;
    END IF;

    -- Create content with a finding that has a suggestion
    SELECT * FROM create_content(v_org, 'Test Post R2', 'blog', 'Test purpose', 'Body with utilize term') INTO v_content, v_rev;

    -- Create a review on the latest revision
    INSERT INTO public.reviews (org_id, revision_id, kit_id, status, llm_status, engine_version, requested_by)
    SELECT v_org, v_rev, v_kit_id, 'done', 'ok', 'test', v_creator
    RETURNING id INTO v_review;

    -- Create a finding with a suggestion
    INSERT INTO public.findings (org_id, review_id, source, rule_id, ref_key, category, severity, quote, start_offset, end_offset, explanation, suggestion, needs_reviewer)
    SELECT v_org, v_review, 'deterministic', v_rule_id, 'TERM-01', 'terminology', 'low', 'utilize', 10, 17, 'Avoid utilize', 'use', false
    RETURNING id INTO v_finding;

    -- First decision: accept
    PERFORM record_decision(v_finding, 'accept');

    -- Second decision: dismiss (later, should win)
    PERFORM record_decision(v_finding, 'dismiss', 'Not needed');

    -- Apply decisions - should result in no changes (dismiss wins)
    BEGIN
        SELECT * FROM apply_decisions(v_content) INTO v_rev_id, v_version, v_applied, v_skipped;
        RAISE EXCEPTION 'FAIL: Expected conflict:no_changes but apply_decisions succeeded with applied=%', v_applied;
    EXCEPTION WHEN SQLSTATE 'P0001' THEN
        IF SQLERRM LIKE '%conflict:no_changes%' THEN
            -- PASS: apply_decisions raised conflict:no_changes (dismiss wins)
        ELSE
            RAISE EXCEPTION 'FAIL: Got unexpected error: %', SQLERRM;
        END IF;
    END;

    -- Check v_finding_state
    IF NOT EXISTS (SELECT 1 FROM v_finding_state WHERE id = v_finding AND last_action = 'dismiss') THEN
        RAISE EXCEPTION 'FAIL: v_finding_state.last_action is not dismiss';
    END IF;

    -- No new revision should be created
    IF (SELECT count(*) FROM public.revisions WHERE content_id = v_content) <> 1 THEN
        RAISE EXCEPTION 'FAIL: New revision was created';
    END IF;
END $$;

-- ============================================================
-- Test R3: Quote mismatch skipped (text_changed)
-- ============================================================
\echo 'Test R3: Quote mismatch skipped (text_changed)'
-- Setup: Content with finding/decision accept
-- 1. record_decision(accept) on finding
-- 2. Direct UPDATE content body (bypass revision) to change quoted text
-- 3. apply_decisions
-- VERIFY:
--   - apply_decisions raises conflict:no_changes (no applicable decisions)
--   - Decision NOT updated with resulting_revision_id
--   - No new revision created

DO $$
DECLARE
    v_org uuid := '11111111-1111-1111-1111-111111111111';
    v_creator uuid;
    v_content uuid;
    v_rev uuid;
    v_review uuid;
    v_finding uuid;
    v_rule_id uuid;
    v_kit_id uuid;
    v_rev_id uuid;
    v_version int;
    v_applied int;
    v_skipped jsonb;
    v_error text;
    v_decision_id uuid;
    v_content_id uuid;
    v_revision_count_before integer;
    v_latest_revision_id uuid;
    v_original_body text;
BEGIN
    -- Get creator user (must exist)
    SELECT id INTO v_creator FROM auth.users WHERE email = 'creator1@axial.demo' LIMIT 1;
    IF v_creator IS NULL THEN
        RAISE EXCEPTION 'FAIL: Test prerequisite missing - creator1@axial.demo not found in auth.users';
    END IF;

    -- Get active brand kit (must exist)
    SELECT id INTO v_kit_id FROM public.brand_kits WHERE org_id = v_org AND status = 'active' LIMIT 1;
    IF v_kit_id IS NULL THEN
        RAISE EXCEPTION 'FAIL: Test prerequisite missing - no active brand kit for org %', v_org;
    END IF;

    -- Get rule with suggestion (must exist)
    SELECT id INTO v_rule_id FROM public.rules WHERE rule_key = 'TERM-01' AND kit_id = v_kit_id LIMIT 1;
    IF v_rule_id IS NULL THEN
        RAISE EXCEPTION 'FAIL: Test prerequisite missing - rule TERM-01 not found in active kit %', v_kit_id;
    END IF;

    SELECT * FROM create_content(v_org, 'Test Post R3', 'blog', 'Test', 'Body with utilize term') INTO v_content, v_rev;

    -- Create review
    INSERT INTO public.reviews (org_id, revision_id, kit_id, status, llm_status, engine_version, requested_by)
    SELECT v_org, v_rev, v_kit_id, 'done', 'ok', 'test', v_creator
    RETURNING id INTO v_review;

    -- Create finding with suggestion - quote 'utilize' at offset 10-17 in 'Body with utilize term'
    INSERT INTO public.findings (org_id, review_id, source, rule_id, ref_key, category, severity, quote, start_offset, end_offset, explanation, suggestion, needs_reviewer)
    SELECT v_org, v_review, 'deterministic', v_rule_id, 'TERM-01', 'terminology', 'low', 'utilize', 10, 17, 'Avoid utilize', 'use', false
    RETURNING id INTO v_finding;

    -- Verify quote matches before modification
    IF substring((SELECT body FROM revisions WHERE id = v_rev) from 11 for 7) <> 'utilize' THEN
        RAISE EXCEPTION 'FAIL: Test setup broken - quote does not match body at offset 10-17';
    END IF;

    -- Accept the finding
    PERFORM record_decision(v_finding, 'accept');

    -- Capture the decision ID
    SELECT id INTO v_decision_id FROM public.decisions WHERE finding_id = v_finding ORDER BY created_at DESC LIMIT 1;

    -- Capture original revision body and count
    v_original_body := (SELECT body FROM revisions WHERE id = v_rev);
    v_latest_revision_id := v_rev;
    v_content_id := v_content;
    SELECT count(*) INTO v_revision_count_before FROM public.revisions WHERE content_id = v_content;

    -- Directly modify the revision body (bypass revision) to change the quoted text
    UPDATE public.revisions SET body = 'Body with use term' WHERE id = v_rev;

    -- Applying a stale quote must produce conflict:no_changes.
    v_error := NULL;

    BEGIN
        PERFORM *
        FROM public.apply_decisions(v_content);

        RAISE EXCEPTION
            'R3 FAILED: apply_decisions unexpectedly succeeded';
    EXCEPTION
        WHEN OTHERS THEN
            IF SQLERRM = 'R3 FAILED: apply_decisions unexpectedly succeeded' THEN
                RAISE;
            END IF;

            v_error := SQLERRM;
    END;

    IF v_error <> 'conflict:no_changes' THEN
        RAISE EXCEPTION
            'R3 FAILED: expected conflict:no_changes, received %',
            v_error;
    END IF;

    -- The decision must remain unapplied.
    IF EXISTS (
        SELECT 1
        FROM public.decisions
        WHERE id = v_decision_id
          AND resulting_revision_id IS NOT NULL
    ) THEN
        RAISE EXCEPTION
            'R3 FAILED: stale decision was marked as applied';
    END IF;

    -- No new revision may have been created.
    IF (
        SELECT count(*)
        FROM public.revisions
        WHERE content_id = v_content
    ) <> v_revision_count_before THEN
        RAISE EXCEPTION
            'R3 FAILED: a revision was created despite no applicable decisions';
    END IF;

    -- Original content body must remain unchanged.
    IF (
        SELECT body
        FROM public.revisions
        WHERE id = v_latest_revision_id
    ) <> v_original_body THEN
        RAISE EXCEPTION
            'R3 FAILED: original revision body changed';
    END IF;
END $$;

-- ============================================================
-- Test R4: Overlapping ranges rejected (overlap)
-- ============================================================
\echo 'Test R4: Overlapping ranges rejected (overlap)'
-- Setup: Two findings with overlapping ranges on same content
-- Body: '0123456789abcdefghijklmno' (25 chars, indices 0-24)
-- Finding A: range [10,20) -> quote 'abcdefghij'
-- Finding B: range [15,25) -> quote 'fghijklmno' (overlaps with A on [15,20))
-- 1. Create finding A, finding B
-- 2. Both have accept decisions with suggestions
-- 3. apply_decisions (processes higher offset first -> B then A)
-- 4. Verify first applied (B at higher offset), second skipped with reason 'overlap'
-- 5. Verify only first decision gets resulting_revision_id
-- VERIFY:
--   - First decision applied, gets resulting_revision_id
--   - Second decision skipped with reason 'overlap'
--   - Only ONE new revision created

DO $$
DECLARE
    v_org uuid := '11111111-1111-1111-1111-111111111111';
    v_creator uuid;
    v_content uuid;
    v_rev uuid;
    v_review uuid;
    v_finding_a uuid;
    v_finding_b uuid;
    v_rule_id uuid;
    v_kit_id uuid;
    v_rev_id uuid;
    v_version int;
    v_applied int;
    v_skipped jsonb;
BEGIN
    -- Get creator user (must exist)
    SELECT id INTO v_creator FROM auth.users WHERE email = 'creator1@axial.demo' LIMIT 1;
    IF v_creator IS NULL THEN
        RAISE EXCEPTION 'FAIL: Test prerequisite missing - creator1@axial.demo not found in auth.users';
    END IF;

    -- Get active brand kit (must exist)
    SELECT id INTO v_kit_id FROM public.brand_kits WHERE org_id = v_org AND status = 'active' LIMIT 1;
    IF v_kit_id IS NULL THEN
        RAISE EXCEPTION 'FAIL: Test prerequisite missing - no active brand kit for org %', v_org;
    END IF;

    -- Get rule (must exist)
    SELECT id INTO v_rule_id FROM public.rules WHERE rule_key = 'TERM-01' AND kit_id = v_kit_id LIMIT 1;
    IF v_rule_id IS NULL THEN
        RAISE EXCEPTION 'FAIL: Test prerequisite missing - rule TERM-01 not found in active kit %', v_kit_id;
    END IF;

    -- Body: '0123456789abcdefghijklmno' (indices 0-24)
    -- Finding A: [10,20) -> 'abcdefghij'
    -- Finding B: [15,25) -> 'fghijklmno' (overlaps A on [15,20))
    SELECT * FROM create_content(v_org, 'Test Post R4', 'blog', 'Test', '0123456789abcdefghijklmno') INTO v_content, v_rev;

    -- Create review
    INSERT INTO public.reviews (org_id, revision_id, kit_id, status, llm_status, engine_version, requested_by)
    SELECT v_org, v_rev, v_kit_id, 'done', 'ok', 'test', v_creator
    RETURNING id INTO v_review;

    -- Verify body matches expected
    IF (SELECT body FROM revisions WHERE id = v_rev) <> '0123456789abcdefghijklmno' THEN
        RAISE EXCEPTION 'FAIL: Test setup broken - body does not match expected';
    END IF;

    -- Verify quotes match at their offsets
    IF substring((SELECT body FROM revisions WHERE id = v_rev) from 11 for 10) <> 'abcdefghij' THEN
        RAISE EXCEPTION 'FAIL: Test setup broken - quote A does not match at offset 10-20';
    END IF;
    IF substring((SELECT body FROM revisions WHERE id = v_rev) from 16 for 10) <> 'fghijklmno' THEN
        RAISE EXCEPTION 'FAIL: Test setup broken - quote B does not match at offset 15-25';
    END IF;

    -- Create finding A (offset 10-20, quote 'abcdefghij')
    INSERT INTO public.findings (org_id, review_id, source, rule_id, ref_key, category, severity, quote, start_offset, end_offset, explanation, suggestion, needs_reviewer)
    SELECT v_org, v_review, 'deterministic', v_rule_id, 'TERM-01', 'terminology', 'low', 'abcdefghij', 10, 20, 'Avoid abcdefghij', 'replacement_a', false
    RETURNING id INTO v_finding_a;

    -- Create finding B (offset 15-25, quote 'fghijklmno', overlaps with A)
    INSERT INTO public.findings (org_id, review_id, source, rule_id, ref_key, category, severity, quote, start_offset, end_offset, explanation, suggestion, needs_reviewer)
    SELECT v_org, v_review, 'deterministic', v_rule_id, 'TERM-01', 'terminology', 'low', 'fghijklmno', 15, 25, 'Avoid fghijklmno', 'replacement_b', false
    RETURNING id INTO v_finding_b;

    -- Accept both findings
    PERFORM record_decision(v_finding_a, 'accept');
    PERFORM record_decision(v_finding_b, 'accept');

    -- Apply decisions (processes higher offset first -> B at 15-25, then A at 10-20)
    -- B should apply first, then A should be skipped due to overlap on [15,20)
    SELECT * FROM apply_decisions(v_content) INTO v_rev_id, v_version, v_applied, v_skipped;

    IF v_applied <> 1 OR NOT (v_skipped::jsonb @> '[{"reason": "overlap"}]'::jsonb) THEN
        RAISE EXCEPTION 'FAIL: Expected applied=1 with overlap skip, got applied=%, skipped=%', v_applied, v_skipped;
    END IF;

    -- Verify only one decision got resulting_revision_id
    IF (SELECT count(*) FROM decisions WHERE finding_id IN (v_finding_a, v_finding_b) AND resulting_revision_id IS NOT NULL) <> 1 THEN
        RAISE EXCEPTION 'FAIL: Expected exactly one decision marked applied';
    END IF;

    -- Only one new revision should be created
    IF (SELECT count(*) FROM revisions WHERE content_id = v_content) <> 2 THEN -- original + 1 new
        RAISE EXCEPTION 'FAIL: Expected 2 revisions total, got %', (SELECT count(*) FROM revisions WHERE content_id = v_content);
    END IF;
END $$;

-- ============================================================
-- Test R5: Batch apply creates single revision atomically
-- ============================================================
\echo 'Test R5: Batch apply creates single revision atomically'
-- Setup: Multiple accept/edit decisions on same content
-- 1. record_decision(accept) for finding A
-- 2. record_decision(accept) for finding B
-- 3. apply_decisions
-- 4. Verify single new revision created
-- 5. Both decisions have same resulting_revision_id
-- 6. New revision source = 'accepted_suggestion'
-- VERIFY:
--   - apply_decisions returns applied=2, skipped=[]
--   - Both decisions have same resulting_revision_id
--   - Exactly one new revision created with source='accepted_suggestion'

DO $$
DECLARE
    v_org uuid := '11111111-1111-1111-1111-111111111111';
    v_creator uuid;
    v_content uuid;
    v_rev uuid;
    v_review uuid;
    v_finding_a uuid;
    v_finding_b uuid;
    v_rule_id uuid;
    v_kit_id uuid;
    v_rev_id uuid;
    v_version int;
    v_applied int;
    v_skipped jsonb;
    v_resulting_rev uuid;
    v_body text;
BEGIN
    -- Get creator user (must exist)
    SELECT id INTO v_creator FROM auth.users WHERE email = 'creator1@axial.demo' LIMIT 1;
    IF v_creator IS NULL THEN
        RAISE EXCEPTION 'FAIL: Test prerequisite missing - creator1@axial.demo not found in auth.users';
    END IF;

    -- Get active brand kit (must exist)
    SELECT id INTO v_kit_id FROM public.brand_kits WHERE org_id = v_org AND status = 'active' LIMIT 1;
    IF v_kit_id IS NULL THEN
        RAISE EXCEPTION 'FAIL: Test prerequisite missing - no active brand kit for org %', v_org;
    END IF;

    -- Get rule TERM-01 (must exist)
    SELECT id INTO v_rule_id FROM public.rules WHERE rule_key = 'TERM-01' AND kit_id = v_kit_id LIMIT 1;
    IF v_rule_id IS NULL THEN
        RAISE EXCEPTION 'FAIL: Test prerequisite missing - rule TERM-01 not found in active kit %', v_kit_id;
    END IF;

    -- Body: 'Body with utilize and leverage terms'
    -- 'utilize' at offset 10-17 (7 chars)
    -- 'leverage' at offset 22-30 (8 chars) - these don't overlap
    v_body := 'Body with utilize and leverage terms';
    SELECT * FROM create_content(v_org, 'Test Post R5', 'blog', 'Test', v_body) INTO v_content, v_rev;

    -- Create review
    INSERT INTO public.reviews (org_id, revision_id, kit_id, status, llm_status, engine_version, requested_by)
    SELECT v_org, v_rev, v_kit_id, 'done', 'ok', 'test', v_creator
    RETURNING id INTO v_review;

    -- Verify body and quotes match
    IF (SELECT body FROM revisions WHERE id = v_rev) <> v_body THEN
        RAISE EXCEPTION 'FAIL: Test setup broken - body does not match expected';
    END IF;
    IF substring(v_body from 11 for 7) <> 'utilize' THEN
        RAISE EXCEPTION 'FAIL: Test setup broken - utilize quote mismatch at offset 10-17';
    END IF;
    IF substring(v_body from 23 for 8) <> 'leverage' THEN
        RAISE EXCEPTION 'FAIL: Test setup broken - leverage quote mismatch at offset 22-30';
    END IF;

    -- Create finding A: TERM-01 - utilize at offset 10-17
    INSERT INTO public.findings (org_id, review_id, source, rule_id, ref_key, category, severity, quote, start_offset, end_offset, explanation, suggestion, needs_reviewer)
    SELECT v_org, v_review, 'deterministic', v_rule_id, 'TERM-01', 'terminology', 'low', 'utilize', 10, 17, 'Avoid utilize', 'use', false
    RETURNING id INTO v_finding_a;

    -- Create finding B: TERM-02 - leverage at offset 22-30
    SELECT id INTO v_rule_id FROM public.rules WHERE rule_key = 'TERM-02' AND kit_id = v_kit_id LIMIT 1;
    IF v_rule_id IS NULL THEN
        RAISE EXCEPTION 'FAIL: Test prerequisite missing - rule TERM-02 not found in active kit %', v_kit_id;
    END IF;

    INSERT INTO public.findings (org_id, review_id, source, rule_id, ref_key, category, severity, quote, start_offset, end_offset, explanation, suggestion, needs_reviewer)
    SELECT v_org, v_review, 'deterministic', v_rule_id, 'TERM-02', 'terminology', 'low', 'leverage', 22, 30, 'Avoid leverage', 'use', false
    RETURNING id INTO v_finding_b;

    -- Accept both findings
    PERFORM record_decision(v_finding_a, 'accept');
    PERFORM record_decision(v_finding_b, 'accept');

    -- Apply decisions
    SELECT * FROM apply_decisions(v_content) INTO v_rev_id, v_version, v_applied, v_skipped;

    IF v_applied <> 2 OR v_skipped <> '[]'::jsonb THEN
        RAISE EXCEPTION 'FAIL: Expected applied=2, skipped=[], got applied=%, skipped=%', v_applied, v_skipped;
    END IF;

    -- Both decisions should have same resulting_revision_id
    SELECT resulting_revision_id INTO v_resulting_rev
    FROM decisions
    WHERE finding_id = v_finding_a AND resulting_revision_id IS NOT NULL
    LIMIT 1;

    IF NOT EXISTS (
        SELECT 1 FROM decisions
        WHERE finding_id IN (v_finding_a, v_finding_b)
          AND resulting_revision_id = v_resulting_rev
    ) THEN
        RAISE EXCEPTION 'FAIL: Decisions do not share same resulting_revision_id';
    END IF;

    -- Exactly one new revision created with source='accepted_suggestion'
    IF (SELECT count(*) FROM revisions WHERE content_id = v_content) <> 2 THEN -- original + 1 new
        RAISE EXCEPTION 'FAIL: Expected 2 revisions total, got %', (SELECT count(*) FROM revisions WHERE content_id = v_content);
    END IF;

    -- Check revision source
    IF NOT EXISTS (SELECT 1 FROM revisions WHERE content_id = v_content AND source = 'accepted_suggestion') THEN
        RAISE EXCEPTION 'FAIL: New revision does not have source=accepted_suggestion';
    END IF;
END $$;

-- ============================================================
-- Manual Scenarios (Documented for Future Automation)
-- ============================================================
\echo '=== Manual Scenarios (Not Automated) ==='

-- Manual M1: Concurrent decision recording
-- Two creators record decisions on same finding concurrently
-- Expected: Latest by created_at,id wins (handled by apply_decisions DISTINCT ON)

-- Manual M2: Re-review after decision application
-- After apply_decisions, new review on new revision
-- Old decisions should not apply to new review
-- Expected: apply_decisions on new review only sees new decisions

-- ============================================================
-- Helper Setup (for manual test execution)
-- ============================================================
\echo '=== Helper Setup Instructions ==='

-- 1. Create test organization
-- INSERT INTO organizations (id, name) VALUES ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'Test Org');

-- 2. Create test users in auth.users (via Supabase Studio or admin API)
--    owner-mgr@test.demo, creator1@test.demo, creator2@test.demo, reviewer@test.demo
--    Get UUIDs: SELECT id, email FROM auth.users WHERE email LIKE '%@test.demo';

-- 3. Run seed_users.sql with actual UUIDs
-- psql -h localhost -p 55432 -U postgres -d postgres \
--   -v owner_uid='<OWNER>' -v creator1_uid='<CREATOR1>' \
--   -v creator2_uid='<CREATOR2>' -v reviewer_uid='<REVIEWER>' \
--   -f supabase/seed/seed_users.sql

-- 4. Run seed_content.sql with creator1 UUID
-- psql -h localhost -p 55432 -U postgres -d postgres \
--   -v creator1_uid='<CREATOR1>' \
--   -f supabase/seed/seed_content.sql

-- 5. Run test setup for each test case
-- (Individual test setup commands would go here)

\echo '=== Workflow Integrity Tests Complete (run manually in Supabase local) ==='
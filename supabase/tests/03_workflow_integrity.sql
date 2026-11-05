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

\echo '=== Workflow Tests Complete (run manually in Supabase local) ==='
/** Tests for data access layer. */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Create mock chain functions
const createMockChain = () => {
  const select = vi.fn().mockReturnThis();
  const eq = vi.fn().mockReturnThis();
  const order = vi.fn().mockReturnThis();
  const limit = vi.fn().mockReturnThis();
  const single = vi.fn().mockResolvedValue({ data: null, error: null });
  const maybeSingle = vi.fn().mockResolvedValue({ data: null, error: null });
  const insert = vi.fn().mockReturnThis();
  const update = vi.fn().mockReturnThis();
  const del = vi.fn().mockReturnThis();
  return { select, eq, order, limit, single, maybeSingle, insert, update, delete: del };
};

// Mock the Supabase client module using vi.mock with factory
const mockAuthGetSession = vi.fn().mockResolvedValue({ data: { session: { access_token: 'test-token' } }, error: null });

vi.mock('../lib/supabase', () => {
  const mockFrom = vi.fn(() => createMockChain());
  const mockRpc = vi.fn().mockResolvedValue({ data: null, error: null });
  return {
    getSupabaseClient: () => ({
      from: mockFrom,
      rpc: mockRpc,
      auth: {
        getSession: mockAuthGetSession,
      },
    }),
    resetSupabaseClient: vi.fn(),
  };
});

// Mock fetch globally
const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

// Import data module AFTER mocking
const dataModule = await import('../lib/data');
const {
  getActiveKit,
  getBrandKits,
  getKitRules,
  getKitFacts,
  getKitStats,
  getContents,
  getContentStats,
  getLatestRevision,
  getRevisions,
  getLatestReviewForRevision,
  getReview,
  getFindingsForReview,
  getFindingsWithDecisionsForReview,
  getPendingSignoffs,
  getRuleStats,
  getContentStatusDistribution,
  getReviewMetrics,
  getFindingInsights,
  createContent,
  createRevision,
  recordDecision,
  applyDecisions,
  submitContent,
  requestChanges,
  recordSignoff,
  approveContent,
  cloneKit,
  activateKit,
  lintKit,
  createReviewPreview,
  confirmReviewPreview,
  uploadVisualAsset,
  updateKitVisualGuidelines,
  updateKitName,
  createRule,
  updateRule,
  deleteRule,
  createFact,
  updateFact,
  deleteFact,
  KitLintError,
  ReviewEngineError,
} = dataModule;

// Get access to the mocked functions for assertions
const { getSupabaseClient } = await import('../lib/supabase');
const mockSupabaseClient = getSupabaseClient();
const mockFrom = mockSupabaseClient.from;
const mockRpc = mockSupabaseClient.rpc;

describe('Data Access Layer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetch.mockReset();
  });

  afterEach(() => {
    // Reset if needed
  });

  describe('Content revision queries', () => {
    it('loads the latest revision from the base table with the canonical id field', async () => {
      const revision = {
        id: 'revision-2',
        org_id: 'org-1',
        content_id: 'content-1',
        version: 2,
        parent_revision_id: 'revision-1',
        body: 'Latest body',
        source: 'manual',
        created_by: 'user-1',
        created_at: '2026-11-12T10:00:00Z',
      };
      const mockChain = createMockChain();
      mockChain.single.mockResolvedValueOnce({ data: revision, error: null });
      mockFrom.mockReturnValueOnce(mockChain);

      const result = await getLatestRevision('content-1');

      expect(mockFrom).toHaveBeenCalledWith('revisions');
      expect(mockChain.select).toHaveBeenCalledWith('*');
      expect(mockChain.eq).toHaveBeenCalledWith('content_id', 'content-1');
      expect(mockChain.order).toHaveBeenCalledWith('version', { ascending: false });
      expect(mockChain.limit).toHaveBeenCalledWith(1);
      expect(result).toEqual(revision);
      expect(result?.id).toBe('revision-2');
    });

    it('returns null when content has no revisions', async () => {
      const mockChain = createMockChain();
      mockChain.single.mockResolvedValueOnce({ data: null, error: { code: 'PGRST116', message: 'No rows' } });
      mockFrom.mockReturnValueOnce(mockChain);

      await expect(getLatestRevision('content-empty')).resolves.toBeNull();
    });
  });

  describe('Review lookup queries', () => {
    it('uses maybeSingle for revisions that do not have a review yet', async () => {
      const mockChain = createMockChain();
      mockChain.maybeSingle.mockResolvedValueOnce({ data: null, error: null });
      mockFrom.mockReturnValueOnce(mockChain);

      await expect(getLatestReviewForRevision('revision-1')).resolves.toBeNull();
      expect(mockFrom).toHaveBeenCalledWith('reviews');
      expect(mockChain.eq).toHaveBeenCalledWith('revision_id', 'revision-1');
      expect(mockChain.maybeSingle).toHaveBeenCalledOnce();
      expect(mockChain.single).not.toHaveBeenCalled();
    });
  });

  describe('RPC function wrappers', () => {
    it('createContent calls create_content RPC with correct args', async () => {
      const mockResult = { content_id: 'content-1', revision_id: 'rev-1' };
      mockRpc.mockResolvedValueOnce({ data: [mockResult], error: null });

      const result = await createContent('org-1', 'Test Title', 'blog', 'Test purpose', 'Test body');

      expect(mockRpc).toHaveBeenCalledWith('create_content', {
        _org: 'org-1',
        _title: 'Test Title',
        _channel: 'blog',
        _purpose: 'Test purpose',
        _body: 'Test body',
      });
      expect(result).toEqual(mockResult);
    });

    it('createRevision calls create_revision RPC', async () => {
      const mockResult = { revision_id: 'rev-2', version: 2 };
      mockRpc.mockResolvedValueOnce({ data: [mockResult], error: null });

      const result = await createRevision('content-1', 'Updated body');

      expect(mockRpc).toHaveBeenCalledWith('create_revision', {
        _content_id: 'content-1',
        _body: 'Updated body',
      });
      expect(result).toEqual(mockResult);
    });

    it('createRevision reports an unchanged body as a duplicate entry', async () => {
      mockRpc.mockResolvedValueOnce({
        data: null,
        error: {
          code: '23505',
          message: 'duplicate_revision',
          details: 'The submitted body is identical to the latest revision.',
        },
      });

      await expect(createRevision('content-1', 'Unchanged body')).rejects.toThrow(
        'Duplicate entry: this content is identical to the latest revision. Make a change before creating a new revision.',
      );
    });

    it('createRevision keeps malformed body errors distinct from duplicates', async () => {
      mockRpc.mockResolvedValueOnce({
        data: null,
        error: { code: 'P0001', message: 'validation:body' },
      });

      await expect(createRevision('content-1', '')).rejects.toThrow(
        'Revision content must be between 1 and 20,000 characters.',
      );
    });

    it('recordDecision calls record_decision RPC with correct args', async () => {
      const mockResult = { decision_id: 'decision-1' };
      mockRpc.mockResolvedValueOnce({ data: [mockResult], error: null });

      const result = await recordDecision('finding-1', 'accept');
      expect(mockRpc).toHaveBeenCalledWith('record_decision', {
        _finding_id: 'finding-1',
        _action: 'accept',
        _reason: null,
        _edited_text: null,
      });
      expect(result).toEqual(mockResult);

      // Test with dismiss and reason
      mockRpc.mockResolvedValueOnce({ data: [{ decision_id: 'decision-2' }], error: null });
      await recordDecision('finding-2', 'dismiss', 'Not applicable');
      expect(mockRpc).toHaveBeenCalledWith('record_decision', {
        _finding_id: 'finding-2',
        _action: 'dismiss',
        _reason: 'Not applicable',
        _edited_text: null,
      });

      // Test with edit and edited_text
      mockRpc.mockResolvedValueOnce({ data: [{ decision_id: 'decision-3' }], error: null });
      await recordDecision('finding-3', 'edit', 'Reason', 'Edited text');
      expect(mockRpc).toHaveBeenCalledWith('record_decision', {
        _finding_id: 'finding-3',
        _action: 'edit',
        _reason: 'Reason',
        _edited_text: 'Edited text',
      });
    });

    it('applyDecisions calls apply_decisions RPC', async () => {
      const mockResult = {
        revision_id: 'rev-3',
        version: 3,
        applied: 2,
        skipped: [{ decision_id: 'd-1', finding_id: 'f-1', reason: 'overlap' }],
      };
      mockRpc.mockResolvedValueOnce({ data: [mockResult], error: null });

      const result = await applyDecisions('content-1');

      expect(mockRpc).toHaveBeenCalledWith('apply_decisions', {
        _content_id: 'content-1',
      });
      expect(result).toEqual(mockResult);
    });

    it('submitContent calls submit_content RPC', async () => {
      mockRpc.mockResolvedValueOnce({ data: null, error: null });

      await submitContent('content-1');

      expect(mockRpc).toHaveBeenCalledWith('submit_content', {
        _content_id: 'content-1',
      });
    });

    it('requestChanges calls request_changes RPC', async () => {
      mockRpc.mockResolvedValueOnce({ data: null, error: null });

      await requestChanges('content-1', 'Please fix the terminology');

      expect(mockRpc).toHaveBeenCalledWith('request_changes', {
        _content_id: 'content-1',
        _note: 'Please fix the terminology',
      });
    });

    it('recordSignoff calls record_signoff RPC', async () => {
      mockRpc.mockResolvedValueOnce({ data: null, error: null });

      await recordSignoff('finding-1', 'signoff');
      expect(mockRpc).toHaveBeenCalledWith('record_signoff', {
        _finding_id: 'finding-1',
        _action: 'signoff',
        _note: null,
      });

      mockRpc.mockResolvedValueOnce({ data: null, error: null });
      await recordSignoff('finding-2', 'reject_claim', 'Claim not supported');
      expect(mockRpc).toHaveBeenCalledWith('record_signoff', {
        _finding_id: 'finding-2',
        _action: 'reject_claim',
        _note: 'Claim not supported',
      });
    });

    it('approveContent calls approve_content RPC', async () => {
      mockRpc.mockResolvedValueOnce({ data: null, error: null });

      await approveContent('content-1');

      expect(mockRpc).toHaveBeenCalledWith('approve_content', {
        _content_id: 'content-1',
      });
    });

    it('cloneKit calls clone_kit RPC', async () => {
      const mockResult = { kit_id: 'kit-new', version: 2 };
      mockRpc.mockResolvedValueOnce({ data: [mockResult], error: null });

      const result = await cloneKit('kit-1');

      expect(mockRpc).toHaveBeenCalledWith('clone_kit', {
        _kit_id: 'kit-1',
      });
      expect(result).toEqual(mockResult);
    });

    it('activateKit calls activate_kit RPC', async () => {
      mockRpc.mockResolvedValueOnce({ data: null, error: null });

      await activateKit('kit-1');

      expect(mockRpc).toHaveBeenCalledWith('activate_kit', {
        _kit_id: 'kit-1',
      });
    });

    it('all RPC wrappers throw on error', async () => {
      mockRpc.mockResolvedValueOnce({ data: null, error: { message: 'RPC failed' } });

      await expect(createContent('org-1', 'Title', 'blog', 'Purpose', 'Body'))
        .rejects.toThrow('Failed to create content: RPC failed');
    });
  });

  describe('Rule CRUD', () => {
    it('createRule inserts rule and returns it', async () => {
      const mockRule = {
        id: 'rule-1',
        org_id: 'org-1',
        kit_id: 'kit-1',
        rule_key: 'TERM-01',
        category: 'terminology',
        title: 'Test Rule',
        guideline_text: 'Use simple terms',
        severity: 'medium',
        check_kind: 'deterministic',
        config: { phrases: ['test'] },
        needs_reviewer: false,
        example_bad: 'utilize',
        example_good: 'use',
      };
      const mockChain = createMockChain();
      mockChain.single.mockResolvedValueOnce({ data: mockRule, error: null });
      mockFrom.mockReturnValueOnce(mockChain);

      const result = await createRule({
        kit_id: 'kit-1',
        rule_key: 'TERM-01',
        category: 'terminology',
        title: 'Test Rule',
        guideline_text: 'Use simple terms',
        severity: 'medium',
        check_kind: 'deterministic',
        config: { phrases: ['test'] },
        needs_reviewer: false,
        example_bad: 'utilize',
        example_good: 'use',
      });

      expect(mockFrom).toHaveBeenCalledWith('rules');
      expect(mockChain.insert).toHaveBeenCalled();
      expect(result).toEqual(mockRule);
    });

    it('updateRule updates rule and returns it', async () => {
      const mockRule = {
        id: 'rule-1',
        org_id: 'org-1',
        kit_id: 'kit-1',
        rule_key: 'TERM-01',
        category: 'terminology',
        title: 'Updated Rule',
        guideline_text: 'Use simple terms',
        severity: 'high',
        check_kind: 'deterministic',
        config: { phrases: ['test'] },
        needs_reviewer: false,
        example_bad: 'utilize',
        example_good: 'use',
      };
      const mockChain = createMockChain();
      mockChain.single.mockResolvedValueOnce({ data: mockRule, error: null });
      mockFrom.mockReturnValueOnce(mockChain);

      const result = await updateRule('rule-1', { title: 'Updated Rule', severity: 'high' });

      expect(mockFrom).toHaveBeenCalledWith('rules');
      expect(mockChain.update).toHaveBeenCalledWith({ title: 'Updated Rule', severity: 'high' });
      expect(mockChain.eq).toHaveBeenCalledWith('id', 'rule-1');
      expect(result).toEqual(mockRule);
    });

    it('deleteRule deletes rule', async () => {
      const mockChain = createMockChain();
      mockChain.single.mockResolvedValueOnce({ data: null, error: null });
      mockFrom.mockReturnValueOnce(mockChain);

      await deleteRule('rule-1');

      expect(mockFrom).toHaveBeenCalledWith('rules');
      expect(mockChain.delete).toHaveBeenCalled();
      expect(mockChain.eq).toHaveBeenCalledWith('id', 'rule-1');
    });

    it('rule mutations throw on error', async () => {
      const mockChain = createMockChain();
      mockChain.single.mockResolvedValueOnce({ data: null, error: { message: 'Insert failed' } });
      mockFrom.mockReturnValueOnce(mockChain);

      await expect(createRule({
        kit_id: 'kit-1',
        rule_key: 'TERM-01',
        category: 'terminology',
        title: 'Test',
        guideline_text: 'Text',
        severity: 'medium',
        check_kind: 'deterministic',
        config: null,
        needs_reviewer: false,
        example_bad: null,
        example_good: null,
      })).rejects.toThrow('Failed to create rule: Insert failed');
    });
  });

  describe('Fact CRUD', () => {
    it('createFact inserts fact and returns it', async () => {
      const mockFact = {
        id: 'fact-1',
        org_id: 'org-1',
        kit_id: 'kit-1',
        fact_key: 'FACT-01',
        statement: 'Test fact',
        source_note: 'Source doc',
        valid_until: '2027-01-01',
      };
      const mockChain = createMockChain();
      mockChain.single.mockResolvedValueOnce({ data: mockFact, error: null });
      mockFrom.mockReturnValueOnce(mockChain);

      const result = await createFact({
        kit_id: 'kit-1',
        fact_key: 'FACT-01',
        statement: 'Test fact',
        source_note: 'Source doc',
        valid_until: '2027-01-01',
      });

      expect(mockFrom).toHaveBeenCalledWith('approved_facts');
      expect(mockChain.insert).toHaveBeenCalled();
      expect(result).toEqual(mockFact);
    });

    it('updateFact updates fact and returns it', async () => {
      const mockFact = {
        id: 'fact-1',
        org_id: 'org-1',
        kit_id: 'kit-1',
        fact_key: 'FACT-01',
        statement: 'Updated fact',
        source_note: 'Source doc',
        valid_until: '2027-01-01',
      };
      const mockChain = createMockChain();
      mockChain.single.mockResolvedValueOnce({ data: mockFact, error: null });
      mockFrom.mockReturnValueOnce(mockChain);

      const result = await updateFact('fact-1', { statement: 'Updated fact' });

      expect(mockFrom).toHaveBeenCalledWith('approved_facts');
      expect(mockChain.update).toHaveBeenCalledWith({ statement: 'Updated fact' });
      expect(mockChain.eq).toHaveBeenCalledWith('id', 'fact-1');
      expect(result).toEqual(mockFact);
    });

    it('deleteFact deletes fact', async () => {
      const mockChain = createMockChain();
      mockChain.single.mockResolvedValueOnce({ data: null, error: null });
      mockFrom.mockReturnValueOnce(mockChain);

      await deleteFact('fact-1');

      expect(mockFrom).toHaveBeenCalledWith('approved_facts');
      expect(mockChain.delete).toHaveBeenCalled();
      expect(mockChain.eq).toHaveBeenCalledWith('id', 'fact-1');
    });
  });

  describe('lintKit', () => {
    const mockLintResponse = {
      ok: true,
      issues: [],
      stats: {
        rules: 5,
        facts: 3,
        llm_rules: 2,
        deterministic_rules: 3,
        prompt_chars_estimate: 5000,
        prompt_chars_cap: 24000,
      },
    };

    beforeEach(() => {
      mockAuthGetSession.mockResolvedValue({ data: { session: { access_token: 'test-token' } }, error: null });
    });

    it('calls lint endpoint with auth token and returns parsed response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockLintResponse,
      });

      const result = await lintKit('kit-1');

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/v1/kits/kit-1/lint'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            Authorization: 'Bearer test-token',
          }),
        })
      );
      expect(result).toEqual(mockLintResponse);
    });

    it('throws ReviewEngineError on 401', async () => {
      mockAuthGetSession.mockResolvedValueOnce({
        data: { session: null },
        error: null,
      });

      let caughtError: unknown;
      try {
        await lintKit('kit-1');
      } catch (e) {
        caughtError = e;
      }
      expect(caughtError).toBeInstanceOf(ReviewEngineError);
      expect(caughtError).toMatchObject({ status: 401 });
    });

    it('throws KitLintError on 403', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 403,
        json: async () => ({ error: { message: 'Forbidden' } }),
      });

      let caughtError: unknown;
      try {
        await lintKit('kit-1');
      } catch (e) {
        caughtError = e;
      }
      expect(caughtError).toBeInstanceOf(KitLintError);
      expect(caughtError).toMatchObject({ status: 403 });
    });

    it('throws KitLintError on 404', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => ({ error: { message: 'Kit not found' } }),
      });

      let caughtError: unknown;
      try {
        await lintKit('kit-1');
      } catch (e) {
        caughtError = e;
      }
      expect(caughtError).toBeInstanceOf(KitLintError);
      expect(caughtError).toMatchObject({ status: 404 });
    });

    it('throws KitLintError on network error', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'));

      let caughtError: unknown;
      try {
        await lintKit('kit-1');
      } catch (e) {
        caughtError = e;
      }
      expect(caughtError).toBeInstanceOf(KitLintError);
      expect(caughtError).toMatchObject({ status: 0 });
    });

    it('throws KitLintError on timeout', async () => {
      const abortError = new DOMException('Aborted', 'AbortError');
      mockFetch.mockRejectedValueOnce(abortError);

      let caughtError: unknown;
      try {
        await lintKit('kit-1');
      } catch (e) {
        caughtError = e;
      }
      expect(caughtError).toBeInstanceOf(KitLintError);
      expect(caughtError).toMatchObject({ status: 504 });
    });

    it('throws KitLintError on invalid response shape', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ invalid: 'shape' }),
      });

      let caughtError: unknown;
      try {
        await lintKit('kit-1');
      } catch (e) {
        caughtError = e;
      }
      expect(caughtError).toBeInstanceOf(KitLintError);
      expect(caughtError).toMatchObject({ status: 500 });
    });
  });
});

// ============================================================
// Mutation/Lint Race Protection Logic Tests
// These test the core logic without rendering the full component
// ============================================================

describe('Mutation/Lint Race Protection Logic', () => {
  // Test the revision counter and lint invalidation logic
  describe('Draft revision counter', () => {
    it('increments revision on mutation start', () => {
      let currentDraftRevision = 0;
      const beginMutation = () => { currentDraftRevision++; };

      beginMutation(); // create rule
      expect(currentDraftRevision).toBe(1);

      beginMutation(); // update rule
      expect(currentDraftRevision).toBe(2);

      beginMutation(); // delete rule
      expect(currentDraftRevision).toBe(3);

      beginMutation(); // create fact
      expect(currentDraftRevision).toBe(4);

      beginMutation(); // update fact
      expect(currentDraftRevision).toBe(5);

      beginMutation(); // delete fact
      expect(currentDraftRevision).toBe(6);
    });

    it('increments revision on kit/org change', () => {
      let currentDraftRevision = 0;
      const invalidateLintAndBumpRevision = () => { currentDraftRevision++; };

      invalidateLintAndBumpRevision();
      expect(currentDraftRevision).toBe(1);
    });
  });

  describe('Pending mutations counter', () => {
    it('increments on mutation start, decrements on completion', () => {
      let pendingMutations = 0;
      const beginMutation = () => { pendingMutations++; };
      const endMutation = () => { pendingMutations = Math.max(0, pendingMutations - 1); };

      beginMutation();
      expect(pendingMutations).toBe(1);

      beginMutation();
      expect(pendingMutations).toBe(2);

      endMutation();
      expect(pendingMutations).toBe(1);

      endMutation();
      expect(pendingMutations).toBe(0);
    });

    it('does not go negative', () => {
      let pendingMutations = 0;
      const endMutation = () => { pendingMutations = Math.max(0, pendingMutations - 1); };

      endMutation();
      expect(pendingMutations).toBe(0);

      endMutation();
      expect(pendingMutations).toBe(0);
    });

    it('handles overlapping mutations correctly', () => {
      let pendingMutations = 0;
      const beginMutation = () => { pendingMutations++; };
      const endMutation = () => { pendingMutations = Math.max(0, pendingMutations - 1); };

      beginMutation(); // mutation 1 starts
      beginMutation(); // mutation 2 starts
      expect(pendingMutations).toBe(2);

      endMutation(); // mutation 1 completes
      expect(pendingMutations).toBe(1); // mutation 2 still pending

      endMutation(); // mutation 2 completes
      expect(pendingMutations).toBe(0);
    });
  });

  describe('Lint revision tracking', () => {
    it('captures revision at lint start', () => {
      let currentDraftRevision = 5;
      let lintRevision = 0;

      const revisionAtStart = currentDraftRevision;
      lintRevision = revisionAtStart;

      expect(lintRevision).toBe(5);
    });

    it('accepts lint result only if revision matches', () => {
      let currentDraftRevision = 5;
      let lintRevision = 0;
      let lintResult = null;

      const revisionAtStart = currentDraftRevision;

      // No mutation occurred
      if (revisionAtStart === currentDraftRevision) {
        lintResult = { ok: true };
        lintRevision = revisionAtStart;
      }

      expect(lintResult).toEqual({ ok: true });
      expect(lintRevision).toBe(5);
    });

    it('rejects lint result if mutation occurred during lint', () => {
      let currentDraftRevision = 5;
      let lintRevision = 0;
      let lintResult = null;

      const revisionAtStart = currentDraftRevision;

      // Mutation occurred during lint
      currentDraftRevision = 6;

      if (revisionAtStart === currentDraftRevision) {
        lintResult = { ok: true };
        lintRevision = revisionAtStart;
      }

      expect(lintResult).toBeNull();
      expect(lintRevision).toBe(0);
    });

    it('rejects lint result if kit changed', () => {
      let currentDraftRevision = 5;
      let lintRevision = 0;
      let lintResult = null;
      let kitId = 'kit-1';

      const revisionAtStart = currentDraftRevision;
      const kitIdAtStart = kitId;

      // Kit changed
      kitId = 'kit-2';

      if (revisionAtStart === currentDraftRevision && kitIdAtStart === kitId) {
        lintResult = { ok: true };
        lintRevision = revisionAtStart;
      }

      expect(lintResult).toBeNull();
    });

    it('rejects lint result if org changed', () => {
      let currentDraftRevision = 5;
      let lintRevision = 0;
      let lintResult = null;
      let orgId = 'org-1';

      const revisionAtStart = currentDraftRevision;
      const orgIdAtStart = orgId;

      // Org changed
      orgId = 'org-2';

      if (revisionAtStart === currentDraftRevision && orgIdAtStart === orgId) {
        lintResult = { ok: true };
        lintRevision = revisionAtStart;
      }

      expect(lintResult).toBeNull();
    });
  });

  describe('Lint request ID protection', () => {
    it('rejects stale lint response when newer request started', () => {
      let lintRequestId = 0;
      let lintResult = null;

      const requestId1 = ++lintRequestId; // 1
      lintRequestId = 2; // newer request started

      if (requestId1 === lintRequestId) {
        lintResult = { ok: true };
      }

      expect(lintResult).toBeNull();
    });

    it('accepts lint response from current request', () => {
      let lintRequestId = 0;
      let lintResult = null;

      const requestId = ++lintRequestId; // 1

      if (requestId === lintRequestId) {
        lintResult = { ok: true };
      }

      expect(lintResult).toEqual({ ok: true });
    });

    it('protects loading state from stale requests', () => {
      let lintRequestId = 0;
      let isLinting = false;

      const requestId1 = ++lintRequestId;
      isLinting = true;

      // Newer request starts
      lintRequestId = 2;

      if (requestId1 === lintRequestId) {
        isLinting = false;
      }

      // Older request should not clear loading for newer request
      expect(isLinting).toBe(true);
    });
  });

  describe('Activation gating logic', () => {
    const checkCanActivate = (
      kitStatus: string,
      lintResult: { ok: boolean } | null,
      lintRevision: number,
      currentDraftRevision: number,
      pendingMutations: number,
      isActivating: boolean
    ) => {
      const isDraft = kitStatus === 'draft';
      const lintMatchesRevision = lintResult !== null && lintRevision === currentDraftRevision;
      const hasSuccessfulLint = lintMatchesRevision && lintResult.ok === true;
      const noPendingMutations = pendingMutations === 0;
      return isDraft && hasSuccessfulLint && noPendingMutations && !isActivating;
    };

    it('allows activation when all conditions met', () => {
      const canActivate = checkCanActivate(
        'draft',
        { ok: true },
        5, // lintRevision
        5, // currentDraftRevision
        0, // pendingMutations
        false // isActivating
      );
      expect(canActivate).toBe(true);
    });

    it('blocks when kit is not draft', () => {
      const canActivate = checkCanActivate(
        'active',
        { ok: true },
        5, 5, 0, false
      );
      expect(canActivate).toBe(false);
    });

    it('blocks when no lint result', () => {
      const canActivate = checkCanActivate(
        'draft',
        null,
        0, 0, 0, false
      );
      expect(canActivate).toBe(false);
    });

    it('blocks when lint revision mismatches', () => {
      const canActivate = checkCanActivate(
        'draft',
        { ok: true },
        4, // old lint revision
        5, // current revision
        0, false
      );
      expect(canActivate).toBe(false);
    });

    it('blocks when lint has errors', () => {
      const canActivate = checkCanActivate(
        'draft',
        { ok: false },
        5, 5, 0, false
      );
      expect(canActivate).toBe(false);
    });

    it('blocks when mutations pending', () => {
      const canActivate = checkCanActivate(
        'draft',
        { ok: true },
        5, 5,
        1, // pending mutation
        false
      );
      expect(canActivate).toBe(false);
    });

    it('blocks when already activating', () => {
      const canActivate = checkCanActivate(
        'draft',
        { ok: true },
        5, 5, 0,
        true // isActivating
      );
      expect(canActivate).toBe(false);
    });

    it('blocks when multiple conditions fail', () => {
      const canActivate = checkCanActivate(
        'active', // wrong status
        { ok: false }, // lint failed
        4, 5, // revision mismatch
        1, // pending
        true // activating
      );
      expect(canActivate).toBe(false);
    });
  });

  describe('Block reason logic', () => {
    const getBlockReason = (
      lintResult: { ok: boolean } | null,
      lintRevision: number,
      currentDraftRevision: number,
      pendingMutations: number
    ) => {
      if (lintResult === null) {
        return 'Run lint to check for issues before activating.';
      }
      if (lintRevision !== currentDraftRevision) {
        return 'Kit has changed since lint completed. Re-run lint.';
      }
      if (!lintResult.ok) {
        return 'Resolve all blocking errors before activation.';
      }
      if (pendingMutations > 0) {
        return 'A rule or fact change is in progress. Wait for it to complete.';
      }
      return null;
    };

    it('returns correct reason for missing lint', () => {
      expect(getBlockReason(null, 0, 0, 0)).toBe('Run lint to check for issues before activating.');
    });

    it('returns correct reason for outdated lint', () => {
      expect(getBlockReason({ ok: true }, 4, 5, 0)).toBe('Kit has changed since lint completed. Re-run lint.');
    });

    it('returns correct reason for failed lint', () => {
      expect(getBlockReason({ ok: false }, 5, 5, 0)).toBe('Resolve all blocking errors before activation.');
    });

    it('returns correct reason for pending mutations', () => {
      expect(getBlockReason({ ok: true }, 5, 5, 1)).toBe('A rule or fact change is in progress. Wait for it to complete.');
    });

    it('returns null when all clear', () => {
      expect(getBlockReason({ ok: true }, 5, 5, 0)).toBeNull();
    });
  });
});

describe('review preview and confirmation API', () => {
  const previewResponse = {
    preview_id: 'preview-1',
    revision_id: 'revision-1',
    confirmation_token: 'one-time-token',
    expires_at: '2026-11-11T12:10:00Z',
    redacted_draft: 'Contact [EMAIL-12345678]',
    text_provider_preview: { system_instruction: 'system', user_content: 'redacted prompt' },
    vision_provider_preview: null,
    assets: [],
    image_consent_required: false,
    redaction_summary: {
      total_matches: 1,
      by_type: { EMAIL: 1 },
      original_chars: 30,
      redacted_chars: 25,
      policy_version: 1,
    },
    payload_sha256: 'a'.repeat(64),
  };
  const confirmResponse = {
    review_id: 'review-1',
    status: 'queued' as const,
    deduplicated: false,
    kit_id: 'kit-1',
    kit_version: 1,
  };

  beforeEach(() => {
    mockAuthGetSession.mockResolvedValue({ data: { session: { access_token: 'test-token' } }, error: null });
  });

  it('creates a preview with the authenticated, no-store request', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => previewResponse });
    const result = await createReviewPreview('revision-1');

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/v1/reviews/preview'),
      expect.objectContaining({
        method: 'POST',
        cache: 'no-store',
        headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
        body: JSON.stringify({ revision_id: 'revision-1' }),
      }),
    );
    expect(result).toEqual(previewResponse);
  });

  it('confirms a preview with explicit image consent', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => confirmResponse });
    const result = await confirmReviewPreview('preview-1', 'one-time-token', true);

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/v1/reviews/confirm'),
      expect.objectContaining({
        method: 'POST',
        cache: 'no-store',
        body: JSON.stringify({
          preview_id: 'preview-1',
          confirmation_token: 'one-time-token',
          consent_to_send_original_images: true,
        }),
      }),
    );
    expect(result).toEqual(confirmResponse);
  });

  it('rejects when there is no authenticated session', async () => {
    mockAuthGetSession.mockResolvedValueOnce({ data: { session: null }, error: null });
    await expect(createReviewPreview('revision-1')).rejects.toMatchObject({
      name: 'ReviewEngineError',
      status: 401,
    });
  });

  it('preserves structured preview errors and machine-readable reason codes', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 409,
      statusText: 'Conflict',
      json: async () => ({ detail: { code: 'preview_expired', message: 'Preview expired' } }),
    });
    await expect(confirmReviewPreview('preview-1', 'token', false)).rejects.toMatchObject({
      name: 'ReviewEngineError',
      status: 409,
      message: expect.stringMatching(/^Preview expired \(Reference ID: .+\)$/),
      reason: 'preview_expired',
    });
  });

  it('parses FastAPI request-validation arrays instead of hiding the cause behind a generic 422', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 422,
      statusText: 'Unprocessable Entity',
      json: async () => ({ detail: [{ loc: ['body', 'revision_id'], msg: 'Input should be a valid UUID', type: 'uuid_parsing' }] }),
    });
    await expect(createReviewPreview('not-a-uuid')).rejects.toMatchObject({
      status: 422,
      reason: 'request_validation_error',
      message: expect.stringMatching(/^Request validation failed: body\.revision_id: Input should be a valid UUID \(Reference ID: .+\)$/),
    });
  });

  it('parses plain FastAPI detail strings', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 400,
      statusText: 'Bad Request',
      json: async () => ({ detail: 'Explicit consent is required' }),
    });
    await expect(confirmReviewPreview('preview-1', 'token', false)).rejects.toMatchObject({
      status: 400,
      message: expect.stringMatching(/^Explicit consent is required \(Reference ID: .+\)$/),
    });
  });

  it('preserves backend request IDs for support diagnostics', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 409,
      statusText: 'Conflict',
      headers: new Headers({ 'X-Request-Id': 'request-correlation-123' }),
      json: async () => ({
        error: {
          code: 'conflict',
          reason: 'preview_expired',
          message: 'Preview expired',
          request_id: 'request-correlation-123',
        },
      }),
    });
    await expect(confirmReviewPreview('preview-1', 'token', false)).rejects.toMatchObject({
      status: 409,
      reason: 'preview_expired',
      requestId: 'request-correlation-123',
      message: 'Preview expired (Reference ID: request-correlation-123)',
    });
  });

  it('converts network errors into ReviewEngineError', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network error'));
    await expect(createReviewPreview('revision-1')).rejects.toMatchObject({
      name: 'ReviewEngineError',
      status: 0,
    });
  });

  it('converts aborts into timeout errors', async () => {
    mockFetch.mockRejectedValueOnce(new DOMException('Aborted', 'AbortError'));
    await expect(createReviewPreview('revision-1')).rejects.toMatchObject({
      name: 'ReviewEngineError',
      status: 504,
    });
  });

  it('rejects malformed preview responses', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ preview_id: 'bad' }) });
    await expect(createReviewPreview('revision-1')).rejects.toMatchObject({
      name: 'ReviewEngineError',
      status: 500,
    });
  });
});

describe('kit name update API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetch.mockReset();
    mockAuthGetSession.mockResolvedValue({
      data: { session: { access_token: 'test-token' } },
      error: null,
    });
  });

  it('saves the name through the authenticated draft-kit endpoint', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ kit_id: 'kit-draft-1', name: 'Campaign Brand Kit' }),
    });

    const result = await updateKitName('kit-draft-1', 'Campaign Brand Kit');

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/v1/kits/kit-draft-1/name'),
      expect.objectContaining({
        method: 'PATCH',
        cache: 'no-store',
        headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
        body: JSON.stringify({ name: 'Campaign Brand Kit' }),
      }),
    );
    expect(result).toBe('Campaign Brand Kit');
  });

  it('surfaces server-side draft immutability errors', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 409,
      statusText: 'Conflict',
      json: async () => ({ detail: { error: { code: 'kit_not_editable', message: 'Only draft kits can be renamed' } } }),
    });

    await expect(updateKitName('kit-active-1', 'Changed')).rejects.toMatchObject({
      status: 409,
      message: 'Only draft kits can be renamed',
    });
  });
});

describe('visual guideline configuration API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetch.mockReset();
    mockAuthGetSession.mockResolvedValue({
      data: { session: { access_token: 'test-token' } },
      error: null,
    });
  });

  it('sends the validated guideline document to the owner API', async () => {
    const visualGuidelines = {
      palette: {
        colors: [{ name: 'Primary', hex: '#123456' }],
        tolerance: 12,
        allow_neutrals: true,
      },
    };
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ kit_id: 'kit-draft-1', visual_guidelines: visualGuidelines }),
    });

    const result = await updateKitVisualGuidelines('kit-draft-1', visualGuidelines);

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/v1/kits/kit-draft-1/visual-guidelines'),
      expect.objectContaining({
        method: 'PUT',
        cache: 'no-store',
        headers: expect.objectContaining({
          Authorization: 'Bearer test-token',
          'Content-Type': 'application/json',
        }),
      }),
    );
    const request = mockFetch.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(request.body as string)).toEqual({ visual_guidelines: visualGuidelines });
    expect(result).toEqual(visualGuidelines);
  });

  it('surfaces server-side draft immutability errors', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 409,
      statusText: 'Conflict',
      json: async () => ({
        detail: {
          error: {
            code: 'kit_not_editable',
            message: 'Visual guidelines can only be changed on draft kits',
          },
        },
      }),
    });

    await expect(updateKitVisualGuidelines('kit-active-1', {})).rejects.toMatchObject({
      status: 409,
      message: 'Visual guidelines can only be changed on draft kits',
    });
  });
});

describe('visual asset upload API', () => {
  const uploadResponse = {
    asset_id: 'asset-visual-1',
    width: 640,
    height: 480,
    mime_type: 'image/png' as const,
    checksum: 'c'.repeat(64),
    signed_url: 'https://storage.example/asset-visual-1.png',
    expires_in: 3600,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockFetch.mockReset();
    mockAuthGetSession.mockResolvedValue({ data: { session: { access_token: 'test-token' } }, error: null });
  });

  it('posts a signature-verified PNG as multipart data with revision association', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => uploadResponse });
    const png = new File([Uint8Array.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])], 'brand.png', { type: 'image/png' });

    const result = await uploadVisualAsset(png, 'content-1', 'revision-1');

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/v1/imports/visual'),
      expect.objectContaining({
        method: 'POST',
        cache: 'no-store',
        headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
      }),
    );
    const request = mockFetch.mock.calls[0][1] as RequestInit;
    expect(request.body).toBeInstanceOf(FormData);
    const body = request.body as FormData;
    expect(body.get('content_id')).toBe('content-1');
    expect(body.get('revision_id')).toBe('revision-1');
    expect((body.get('file') as Blob).type).toBe('image/png');
    expect(request.headers).not.toHaveProperty('Content-Type');
    expect(result).toEqual(uploadResponse);
  });

  it('accepts JPEG and WebP signatures even when the browser omits File.type', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ ...uploadResponse, mime_type: 'image/jpeg' }) });
    const jpeg = new File([Uint8Array.from([0xff, 0xd8, 0xff, 0x00])], 'photo.jpg');
    await uploadVisualAsset(jpeg, 'content-1', 'revision-1');
    const jpegRequest = mockFetch.mock.calls[0][1] as RequestInit;
    expect(((jpegRequest.body as FormData).get('file') as Blob).type).toBe('image/jpeg');

    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ ...uploadResponse, mime_type: 'image/webp' }) });
    const webp = new File([Uint8Array.from([0x52, 0x49, 0x46, 0x46, 0, 0, 0, 0, 0x57, 0x45, 0x42, 0x50])], 'graphic.webp');
    await uploadVisualAsset(webp, 'content-1', 'revision-1');
    const webpRequest = mockFetch.mock.calls[1][1] as RequestInit;
    expect(((webpRequest.body as FormData).get('file') as Blob).type).toBe('image/webp');
  });

  it('rejects unsupported formats based on file signature before making a request', async () => {
    const gif = new File([Uint8Array.from([0x47, 0x49, 0x46, 0x38, 0x39, 0x61])], 'animation.gif', { type: 'image/gif' });
    await expect(uploadVisualAsset(gif, 'content-1', 'revision-1')).rejects.toMatchObject({
      status: 415,
      message: 'Unsupported image. Choose a PNG, JPG/JPEG, or WebP file.',
    });
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('rejects images above the 10 MB backend limit before making a request', async () => {
    const oversized = new File([new Uint8Array(10 * 1024 * 1024 + 1)], 'large.png', { type: 'image/png' });
    await expect(uploadVisualAsset(oversized, 'content-1', 'revision-1')).rejects.toMatchObject({
      status: 413,
      message: 'Each image must be 10 MB or smaller.',
    });
    expect(mockFetch).not.toHaveBeenCalled();
  });
});

describe('Insights queries', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetch.mockReset();
  });

  // Helper to create a thenable mock chain for array-returning queries
  const createThenableMockChain = (resolveData: unknown) => {
    const chain = createMockChain();
    // Make the chain thenable by adding a then method that returns a resolved promise
    chain.then = (onFulfilled?: (value: unknown) => unknown) => {
      return Promise.resolve(resolveData).then(onFulfilled);
    };
    // Ensure select, eq, order return the chain for chaining
    chain.select.mockReturnThis();
    chain.eq.mockReturnThis();
    chain.order.mockReturnThis();
    chain.limit.mockReturnThis();
    return chain;
  };

  describe('getContentStatusDistribution', () => {
    it('returns distribution with all statuses', async () => {
      const mockData = [
        { status: 'draft' },
        { status: 'submitted' },
        { status: 'submitted' },
        { status: 'changes_requested' },
        { status: 'approved' },
        { status: 'approved' },
        { status: 'approved' },
      ];
      const mockChain = createThenableMockChain({ data: mockData, error: null });
      mockFrom.mockReturnValueOnce(mockChain);

      const result = await getContentStatusDistribution('org-1');

      expect(mockFrom).toHaveBeenCalledWith('contents');
      expect(mockChain.select).toHaveBeenCalledWith('status');
      expect(mockChain.eq).toHaveBeenCalledWith('org_id', 'org-1');
      expect(result).toEqual({
        draft: 1,
        submitted: 2,
        changes_requested: 1,
        approved: 3,
        total: 7,
      });
    });

    it('returns zero distribution when no content', async () => {
      const mockChain = createThenableMockChain({ data: [], error: null });
      mockFrom.mockReturnValueOnce(mockChain);

      const result = await getContentStatusDistribution('org-1');

      expect(result).toEqual({
        draft: 0,
        submitted: 0,
        changes_requested: 0,
        approved: 0,
        total: 0,
      });
    });

    it('throws on error', async () => {
      const mockChain = createThenableMockChain({ data: null, error: { message: 'Query failed' } });
      mockFrom.mockReturnValueOnce(mockChain);

      await expect(getContentStatusDistribution('org-1')).rejects.toThrow(
        'Failed to fetch content status distribution: Query failed'
      );
    });
  });

  describe('getReviewMetrics', () => {
    it('returns metrics with all review statuses and LLM statuses', async () => {
      const mockData = [
        { status: 'done', llm_status: 'ok', llm_findings_raw: 10, llm_findings_dropped: 2 },
        { status: 'done', llm_status: 'skipped', llm_findings_raw: 0, llm_findings_dropped: 0 },
        { status: 'done', llm_status: 'failed', llm_findings_raw: 5, llm_findings_dropped: 5 },
        { status: 'queued', llm_status: 'ok', llm_findings_raw: 0, llm_findings_dropped: 0 },
        { status: 'running', llm_status: 'ok', llm_findings_raw: 0, llm_findings_dropped: 0 },
        { status: 'failed', llm_status: 'failed', llm_findings_raw: 0, llm_findings_dropped: 0 },
      ];
      const mockChain = createThenableMockChain({ data: mockData, error: null });
      mockFrom.mockReturnValueOnce(mockChain);

      const result = await getReviewMetrics('org-1');

      expect(mockFrom).toHaveBeenCalledWith('reviews');
      expect(mockChain.select).toHaveBeenCalledWith('status, llm_status, llm_findings_raw, llm_findings_dropped');
      expect(mockChain.eq).toHaveBeenCalledWith('org_id', 'org-1');
      expect(result).toEqual({
        total_reviews: 6,
        queued: 1,
        running: 1,
        done: 3,
        failed: 1,
        llm_ok: 3,
        llm_skipped: 1,
        llm_failed: 2,
        total_llm_findings_raw: 15,
        total_llm_findings_dropped: 7,
        validator_drop_rate: 0.4667,
      });
    });

    it('returns zero metrics when no reviews', async () => {
      const mockChain = createThenableMockChain({ data: [], error: null });
      mockFrom.mockReturnValueOnce(mockChain);

      const result = await getReviewMetrics('org-1');

      expect(result).toEqual({
        total_reviews: 0,
        queued: 0,
        running: 0,
        done: 0,
        failed: 0,
        llm_ok: 0,
        llm_skipped: 0,
        llm_failed: 0,
        total_llm_findings_raw: 0,
        total_llm_findings_dropped: 0,
        validator_drop_rate: 0,
      });
    });

    it('calculates validator drop rate correctly', async () => {
      const mockData = [
        { status: 'done', llm_status: 'ok', llm_findings_raw: 100, llm_findings_dropped: 25 },
      ];
      const mockChain = createThenableMockChain({ data: mockData, error: null });
      mockFrom.mockReturnValueOnce(mockChain);

      const result = await getReviewMetrics('org-1');
      expect(result.validator_drop_rate).toBe(0.25);
    });

    it('handles null llm_findings values', async () => {
      const mockData = [
        { status: 'done', llm_status: 'ok', llm_findings_raw: null, llm_findings_dropped: null },
      ];
      const mockChain = createThenableMockChain({ data: mockData, error: null });
      mockFrom.mockReturnValueOnce(mockChain);

      const result = await getReviewMetrics('org-1');
      expect(result.total_llm_findings_raw).toBe(0);
      expect(result.total_llm_findings_dropped).toBe(0);
    });

    it('throws on error', async () => {
      const mockChain = createThenableMockChain({ data: null, error: { message: 'Query failed' } });
      mockFrom.mockReturnValueOnce(mockChain);

      await expect(getReviewMetrics('org-1')).rejects.toThrow(
        'Failed to fetch review metrics: Query failed'
      );
    });
  });

  describe('getFindingInsights', () => {
    const mockFindings = [
      {
        id: 'f1',
        org_id: 'org-1',
        review_id: 'r1',
        ref_key: 'TERM-01',
        category: 'terminology',
        severity: 'low',
        last_action: 'accept',
        last_reason: null,
      },
      {
        id: 'f2',
        org_id: 'org-1',
        review_id: 'r1',
        ref_key: 'TERM-01',
        category: 'terminology',
        severity: 'low',
        last_action: 'dismiss',
        last_reason: 'Not applicable to this context',
      },
      {
        id: 'f3',
        org_id: 'org-1',
        review_id: 'r1',
        ref_key: 'CLAIM-01',
        category: 'claim',
        severity: 'high',
        last_action: 'edit',
        last_reason: null,
      },
      {
        id: 'f4',
        org_id: 'org-1',
        review_id: 'r1',
        ref_key: 'TONE-01',
        category: 'tone',
        severity: 'medium',
        last_action: null,
        last_reason: null,
      },
      {
        id: 'f5',
        org_id: 'org-1',
        review_id: 'r1',
        ref_key: 'A11Y-01',
        category: 'accessibility',
        severity: 'high',
        last_action: 'dismiss',
        last_reason: 'Fixed in revision',
      },
      {
        id: 'f6',
        org_id: 'org-1',
        review_id: 'r1',
        ref_key: 'A11Y-01',
        category: 'accessibility',
        severity: 'high',
        last_action: 'dismiss',
        last_reason: 'Fixed in revision',
      },
    ];

    it('returns insights with correct decision counts and distributions', async () => {
      // Mock v_finding_state query
      const mockChain1 = createThenableMockChain({ data: mockFindings, error: null });
      mockFrom.mockReturnValueOnce(mockChain1);

      // Mock getRuleStats (v_rule_stats query)
      const mockChain2 = createThenableMockChain({
        data: [
          { org_id: 'org-1', ref_key: 'TERM-01', category: 'terminology', findings: 2, dismissed: 1, acted_on: 1, dismissal_rate: 0.5, last_seen: '2026-11-01T00:00:00Z' },
          { org_id: 'org-1', ref_key: 'CLAIM-01', category: 'claim', findings: 1, dismissed: 0, acted_on: 1, dismissal_rate: 0, last_seen: '2026-11-01T00:00:00Z' },
          { org_id: 'org-1', ref_key: 'TONE-01', category: 'tone', findings: 1, dismissed: 0, acted_on: 0, dismissal_rate: 0, last_seen: '2026-11-01T00:00:00Z' },
          { org_id: 'org-1', ref_key: 'A11Y-01', category: 'accessibility', findings: 2, dismissed: 2, acted_on: 0, dismissal_rate: 1, last_seen: '2026-11-01T00:00:00Z' },
        ],
        error: null,
      });
      mockFrom.mockReturnValueOnce(mockChain2);

      const result = await getFindingInsights('org-1');

      expect(result.total_findings).toBe(6);
      expect(result.accepted).toBe(1);
      expect(result.edited).toBe(1);
      expect(result.dismissed).toBe(3);
      expect(result.pending_decision).toBe(1);
      expect(result.by_severity).toEqual({ low: 2, high: 3, medium: 1 });
      expect(result.by_category).toEqual({ terminology: 2, claim: 1, tone: 1, accessibility: 2 });
      expect(result.dismissal_reasons).toEqual([
        { reason: 'Fixed in revision', count: 2 },
        { reason: 'Not applicable to this context', count: 1 },
      ]);
      expect(result.by_rule).toHaveLength(4);
    });

    it('returns empty insights when no findings', async () => {
      const mockChain1 = createThenableMockChain({ data: [], error: null });
      mockFrom.mockReturnValueOnce(mockChain1);

      const mockChain2 = createThenableMockChain({ data: [], error: null });
      mockFrom.mockReturnValueOnce(mockChain2);

      const result = await getFindingInsights('org-1');

      expect(result).toEqual({
        total_findings: 0,
        accepted: 0,
        edited: 0,
        dismissed: 0,
        pending_decision: 0,
        by_rule: [],
        by_severity: {},
        by_category: {},
        dismissal_reasons: [],
      });
    });

    it('handles dismissal reasons with empty/null values', async () => {
      const findingsWithEmptyReasons = [
        { id: 'f1', org_id: 'org-1', review_id: 'r1', ref_key: 'TERM-01', category: 'terminology', severity: 'low', last_action: 'dismiss', last_reason: '' },
        { id: 'f2', org_id: 'org-1', review_id: 'r1', ref_key: 'TERM-02', category: 'terminology', severity: 'low', last_action: 'dismiss', last_reason: null },
        { id: 'f3', org_id: 'org-1', review_id: 'r1', ref_key: 'TERM-03', category: 'terminology', severity: 'low', last_action: 'dismiss', last_reason: '  ' },
      ];

      const mockChain1 = createThenableMockChain({ data: findingsWithEmptyReasons, error: null });
      mockFrom.mockReturnValueOnce(mockChain1);

      const mockChain2 = createThenableMockChain({ data: [], error: null });
      mockFrom.mockReturnValueOnce(mockChain2);

      const result = await getFindingInsights('org-1');

      expect(result.dismissed).toBe(3);
      expect(result.dismissal_reasons).toEqual([]);
    });

    it('throws on v_finding_state error', async () => {
      const mockChain1 = createThenableMockChain({ data: null, error: { message: 'Query failed' } });
      mockFrom.mockReturnValueOnce(mockChain1);

      await expect(getFindingInsights('org-1')).rejects.toThrow(
        'Failed to fetch finding insights: Query failed'
      );
    });

    it('throws on v_rule_stats error', async () => {
      const mockChain1 = createThenableMockChain({ data: [], error: null });
      mockFrom.mockReturnValueOnce(mockChain1);

      const mockChain2 = createThenableMockChain({ data: null, error: { message: 'Rule stats failed' } });
      mockFrom.mockReturnValueOnce(mockChain2);

      await expect(getFindingInsights('org-1')).rejects.toThrow(
        'Failed to fetch rule stats: Rule stats failed'
      );
    });
  });
});

describe('getEngineUrl', () => {
  const originalEnv = import.meta.env;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns development fallback when VITE_ENGINE_URL not set in development', async () => {
    vi.stubGlobal('import.meta', { ...originalEnv, env: { ...originalEnv, VITE_ENGINE_URL: undefined, PROD: false } });
    const { getEngineUrl } = await import('../lib/data');
    expect(getEngineUrl()).toBe('http://localhost:8000');
  });
});

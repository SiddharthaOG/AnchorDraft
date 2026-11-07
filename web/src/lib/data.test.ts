/** Tests for data access layer. */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Create mock chain functions
const createMockChain = () => {
  const select = vi.fn().mockReturnThis();
  const eq = vi.fn().mockReturnThis();
  const order = vi.fn().mockReturnThis();
  const limit = vi.fn().mockReturnThis();
  const single = vi.fn().mockResolvedValue({ data: null, error: null });
  const insert = vi.fn().mockReturnThis();
  const update = vi.fn().mockReturnThis();
  return { select, eq, order, limit, single, insert, update };
};

// Mock the Supabase client module using vi.mock with factory
vi.mock('../lib/supabase', () => {
  const mockFrom = vi.fn(() => createMockChain());
  const mockRpc = vi.fn().mockResolvedValue({ data: null, error: null });
  return {
    getSupabaseClient: () => ({
      from: mockFrom,
      rpc: mockRpc,
    }),
    resetSupabaseClient: vi.fn(),
  };
});

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
} = dataModule;

// Get access to the mocked functions for assertions
const { getSupabaseClient } = await import('../lib/supabase');
const mockSupabaseClient = getSupabaseClient();
const mockFrom = mockSupabaseClient.from;
const mockRpc = mockSupabaseClient.rpc;

describe('Data Access Layer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    // Reset if needed
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
});
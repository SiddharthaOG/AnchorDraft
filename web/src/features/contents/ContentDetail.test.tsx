/** Tests for ContentDetail component - revision editor behavior. */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup, fireEvent, act } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { ContentDetail } from './ContentDetail';

// Mock the data layer using vi.hoisted
const {
  mockGetContents,
  mockGetLatestRevision,
  mockGetRevisions,
  mockGetLatestReviewForRevision,
  mockGetFindingsWithDecisionsForReview,
  mockGetPendingSignoffs,
  mockCreateRevision,
  mockSubmitContent,
  mockStartReview,
  mockRecordDecision,
  mockApplyDecisions,
} = vi.hoisted(() => ({
  mockGetContents: vi.fn(),
  mockGetLatestRevision: vi.fn(),
  mockGetRevisions: vi.fn(),
  mockGetLatestReviewForRevision: vi.fn(),
  mockGetFindingsWithDecisionsForReview: vi.fn(),
  mockGetPendingSignoffs: vi.fn(),
  mockCreateRevision: vi.fn(),
  mockSubmitContent: vi.fn(),
  mockStartReview: vi.fn(),
  mockRecordDecision: vi.fn(),
  mockApplyDecisions: vi.fn(),
}));

vi.mock('../../lib/data', () => ({
  getContents: mockGetContents,
  getLatestRevision: mockGetLatestRevision,
  getRevisions: mockGetRevisions,
  getLatestReviewForRevision: mockGetLatestReviewForRevision,
  getFindingsWithDecisionsForReview: mockGetFindingsWithDecisionsForReview,
  getPendingSignoffs: mockGetPendingSignoffs,
  createRevision: mockCreateRevision,
  submitContent: mockSubmitContent,
  startReview: mockStartReview,
  recordDecision: mockRecordDecision,
  applyDecisions: mockApplyDecisions,
}));

// Mock the auth service using vi.hoisted
const { mockSession: mockCreatorSession } = vi.hoisted(() => ({
  mockSession: {
    user: { id: 'user-1', email: 'creator@example.com' },
    profile: { display_name: 'Test Creator', user_id: 'user-1', created_at: '2026-01-01' },
    memberships: [{ org_id: 'org-1', user_id: 'user-1', roles: ['creator'], created_at: '2026-01-01' }],
    organizations: [{ id: 'org-1', name: 'Test Org', created_at: '2026-01-01' }],
    currentOrgId: 'org-1',
    currentOrgName: 'Test Org',
    currentRoles: ['creator'],
    isLoading: false,
    error: null,
  },
}));

vi.mock('../../features/auth/AuthProvider', () => ({
  useAuth: () => ({
    session: mockCreatorSession,
    isLoading: false,
    error: null,
    signInWithEmail: vi.fn(),
    signInWithOAuth: vi.fn(),
    signOut: vi.fn(),
    switchOrganization: vi.fn(),
    hasRole: vi.fn((role: string) => mockCreatorSession.currentRoles.includes(role)),
    hasAnyRole: vi.fn((roles: string[]) => roles.some(role => mockCreatorSession.currentRoles.includes(role))),
    getPrimaryRole: vi.fn(() => 'creator'),
    refreshSession: vi.fn(),
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));

// Default test content data
const defaultContent = {
  id: 'content-1',
  org_id: 'org-1',
  title: 'Test Blog Post',
  channel: 'blog' as const,
  purpose: 'Test purpose',
  status: 'draft' as const,
  created_by: 'user-1',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const defaultRevision = {
  id: 'revision-1',
  org_id: 'org-1',
  content_id: 'content-1',
  version: 1,
  parent_revision_id: null,
  body: 'Original content body',
  source: 'manual' as const,
  created_by: 'user-1',
  created_at: '2026-01-01T00:00:00Z',
};

const defaultRevisions = [defaultRevision];

const defaultReview = {
  id: 'review-1',
  org_id: 'org-1',
  revision_id: 'revision-1',
  kit_id: 'kit-1',
  status: 'done' as const,
  error: null,
  engine_version: '1.0.0',
  model: 'test-model',
  prompt_version: 'p1',
  llm_status: 'ok' as const,
  warnings: [],
  llm_findings_raw: 0,
  llm_findings_dropped: 0,
  validator_stats: {},
  requested_by: 'user-1',
  created_at: '2026-01-01T00:00:00Z',
  started_at: '2026-01-01T00:00:00Z',
  finished_at: '2026-01-01T00:00:00Z',
};

const defaultFindings: any[] = [];
const defaultSignoffs: any[] = [];

describe('ContentDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockGetContents.mockResolvedValue([defaultContent]);
    mockGetLatestRevision.mockResolvedValue(defaultRevision);
    mockGetRevisions.mockResolvedValue(defaultRevisions);
    mockGetLatestReviewForRevision.mockResolvedValue(defaultReview);
    mockGetFindingsWithDecisionsForReview.mockResolvedValue(defaultFindings);
    mockGetPendingSignoffs.mockResolvedValue(defaultSignoffs);
    mockCreateRevision.mockResolvedValue({ revision_id: 'revision-2', version: 2 });
    mockSubmitContent.mockResolvedValue(undefined);
    mockStartReview.mockResolvedValue({ review_id: 'review-2', status: 'queued', deduplicated: false, kit_id: 'kit-1', kit_version: 1 });
    mockRecordDecision.mockResolvedValue({ decision_id: 'decision-1' });
    mockApplyDecisions.mockResolvedValue({ revision_id: 'revision-2', version: 2, applied: 1, skipped: [] });
  });

  afterEach(() => {
    cleanup();
  });

  function TestWrapper({ children }: { children: React.ReactNode }) {
    return (
      <MemoryRouter initialEntries={['/contents/content-1']}>
        <Routes>
          <Route
            path="/contents/:contentId"
            element={<>{children}</>}
          />
        </Routes>
      </MemoryRouter>
    );
  }

  async function renderAndWaitForLoad(component: React.ReactElement) {
    await act(async () => {
      render(component, { wrapper: TestWrapper });
      // Let all microtasks run
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    // Wait for loading to complete
    await waitFor(() => {
      expect(screen.queryByText('Loading content...')).not.toBeInTheDocument();
    }, { timeout: 10000 });
  }

  describe('Revision Editor Visibility', () => {
    it('shows "New Revision" button when content is editable and no editor is open', async () => {
      await renderAndWaitForLoad(<ContentDetail />);

      expect(screen.getByRole('button', { name: 'New Revision' })).toBeInTheDocument();
      // Editor should not be visible initially
      expect(screen.queryByText('Create New Revision')).not.toBeInTheDocument();
    }, { timeout: 15000 });

    it('opens the revision editor when "New Revision" is clicked', async () => {
      await renderAndWaitForLoad(<ContentDetail />);

      // Click New Revision
      const newRevisionBtn = screen.getByRole('button', { name: 'New Revision' });
      fireEvent.click(newRevisionBtn);

      // Editor should be visible
      await waitFor(() => {
        expect(screen.getByText('Create New Revision')).toBeInTheDocument();
      });

      // Textarea should have the original content
      const textarea = screen.getByPlaceholderText('Edit content for new revision...');
      expect(textarea).toHaveValue('Original content body');

      // Cancel button should be present
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    }, { timeout: 15000 });

    it('does not disable Create Revision button when editor opens', async () => {
      await renderAndWaitForLoad(<ContentDetail />);

      fireEvent.click(screen.getByRole('button', { name: 'New Revision' }));

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Create Revision' })).not.toBeDisabled();
      });
    }, { timeout: 15000 });

    it('closes editor when Cancel is clicked without calling createRevision', async () => {
      await renderAndWaitForLoad(<ContentDetail />);

      fireEvent.click(screen.getByRole('button', { name: 'New Revision' }));

      await waitFor(() => {
        expect(screen.getByText('Create New Revision')).toBeInTheDocument();
      });

      // Click Cancel
      fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

      // Editor should close
      await waitFor(() => {
        expect(screen.queryByText('Create New Revision')).not.toBeInTheDocument();
      });

      // createRevision should not have been called
      expect(mockCreateRevision).not.toHaveBeenCalled();
    }, { timeout: 15000 });

    it('closes editor when X button is clicked', async () => {
      await renderAndWaitForLoad(<ContentDetail />);

      fireEvent.click(screen.getByRole('button', { name: 'New Revision' }));

      await waitFor(() => {
        expect(screen.getByText('Create New Revision')).toBeInTheDocument();
      });

      // Click X button (the close button)
      const closeBtn = screen.getByText('×');
      fireEvent.click(closeBtn);

      // Editor should close
      await waitFor(() => {
        expect(screen.queryByText('Create New Revision')).not.toBeInTheDocument();
      });
    }, { timeout: 15000 });
  });

  describe('Revision Creation Submission', () => {
    it('calls createRevision with exact textarea content when Create Revision button is clicked', async () => {
      await renderAndWaitForLoad(<ContentDetail />);

      fireEvent.click(screen.getByRole('button', { name: 'New Revision' }));

      await waitFor(() => {
        expect(screen.getByText('Create New Revision')).toBeInTheDocument();
      });

      // Edit the textarea
      const textarea = screen.getByPlaceholderText('Edit content for new revision...');
      fireEvent.change(textarea, { target: { value: 'Updated content body' } });

      // Click Create Revision
      fireEvent.click(screen.getByRole('button', { name: 'Create Revision' }));

      // Wait for mutation to complete
      await waitFor(() => {
        expect(mockCreateRevision).toHaveBeenCalledTimes(1);
      });

      expect(mockCreateRevision).toHaveBeenCalledWith('content-1', 'Updated content body');

      // Editor should close on success
      await waitFor(() => {
        expect(screen.queryByText('Create New Revision')).not.toBeInTheDocument();
      });
    }, { timeout: 15000 });

    it('submits same content via Ctrl+Enter shortcut', async () => {
      await renderAndWaitForLoad(<ContentDetail />);

      fireEvent.click(screen.getByRole('button', { name: 'New Revision' }));

      await waitFor(() => {
        expect(screen.getByText('Create New Revision')).toBeInTheDocument();
      });

      // Edit the textarea
      const textarea = screen.getByPlaceholderText('Edit content for new revision...');
      fireEvent.change(textarea, { target: { value: 'Ctrl+Enter content' } });

      // Press Ctrl+Enter
      fireEvent.keyDown(textarea, { key: 'Enter', ctrlKey: true });

      // Wait for mutation to complete
      await waitFor(() => {
        expect(mockCreateRevision).toHaveBeenCalledTimes(1);
      });

      expect(mockCreateRevision).toHaveBeenCalledWith('content-1', 'Ctrl+Enter content');

      // Editor should close on success
      await waitFor(() => {
        expect(screen.queryByText('Create New Revision')).not.toBeInTheDocument();
      });
    }, { timeout: 15000 });

    it('submits same content via Meta+Enter shortcut (Mac)', async () => {
      await renderAndWaitForLoad(<ContentDetail />);

      fireEvent.click(screen.getByRole('button', { name: 'New Revision' }));

      await waitFor(() => {
        expect(screen.getByText('Create New Revision')).toBeInTheDocument();
      });

      // Edit the textarea
      const textarea = screen.getByPlaceholderText('Edit content for new revision...');
      fireEvent.change(textarea, { target: { value: 'Meta+Enter content' } });

      // Press Meta+Enter (Cmd+Enter on Mac)
      fireEvent.keyDown(textarea, { key: 'Enter', metaKey: true });

      // Wait for mutation to complete
      await waitFor(() => {
        expect(mockCreateRevision).toHaveBeenCalledTimes(1);
      });

      expect(mockCreateRevision).toHaveBeenCalledWith('content-1', 'Meta+Enter content');
    }, { timeout: 15000 });

    it('rejects empty content with error message', async () => {
      await renderAndWaitForLoad(<ContentDetail />);

      fireEvent.click(screen.getByRole('button', { name: 'New Revision' }));

      await waitFor(() => {
        expect(screen.getByText('Create New Revision')).toBeInTheDocument();
      });

      // Clear the textarea
      const textarea = screen.getByPlaceholderText('Edit content for new revision...');
      fireEvent.change(textarea, { target: { value: '' } });

      // Click Create Revision
      fireEvent.click(screen.getByRole('button', { name: 'Create Revision' }));

      // Should show error toast
      await waitFor(() => {
        expect(screen.getByText('Revision content cannot be empty')).toBeInTheDocument();
      });

      // createRevision should not have been called
      expect(mockCreateRevision).not.toHaveBeenCalled();

      // Editor should remain open
      expect(screen.getByText('Create New Revision')).toBeInTheDocument();
    }, { timeout: 15000 });

    it('rejects whitespace-only content with error message', async () => {
      await renderAndWaitForLoad(<ContentDetail />);

      fireEvent.click(screen.getByRole('button', { name: 'New Revision' }));

      await waitFor(() => {
        expect(screen.getByText('Create New Revision')).toBeInTheDocument();
      });

      // Set whitespace-only content
      const textarea = screen.getByPlaceholderText('Edit content for new revision...');
      fireEvent.change(textarea, { target: { value: '   \n\t  ' } });

      // Click Create Revision
      fireEvent.click(screen.getByRole('button', { name: 'Create Revision' }));

      // Should show error toast
      await waitFor(() => {
        expect(screen.getByText('Revision content cannot be empty')).toBeInTheDocument();
      });

      // createRevision should not have been called
      expect(mockCreateRevision).not.toHaveBeenCalled();

      // Editor should remain open
      expect(screen.getByText('Create New Revision')).toBeInTheDocument();
    }, { timeout: 15000 });

    it('prevents duplicate submissions when double-clicking Create Revision', async () => {
      await renderAndWaitForLoad(<ContentDetail />);

      fireEvent.click(screen.getByRole('button', { name: 'New Revision' }));

      await waitFor(() => {
        expect(screen.getByText('Create New Revision')).toBeInTheDocument();
      });

      const textarea = screen.getByPlaceholderText('Edit content for new revision...');
      fireEvent.change(textarea, { target: { value: 'Test content' } });

      // Double-click Create Revision rapidly
      const createBtn = screen.getByRole('button', { name: 'Create Revision' });
      fireEvent.click(createBtn);
      fireEvent.click(createBtn);

      // Wait for mutation
      await waitFor(() => {
        expect(mockCreateRevision).toHaveBeenCalledTimes(1);
      });

      // Should only be called once
      expect(mockCreateRevision).toHaveBeenCalledTimes(1);
    }, { timeout: 15000 });

    it('prevents duplicate submissions via button click and Ctrl+Enter', async () => {
      await renderAndWaitForLoad(<ContentDetail />);

      fireEvent.click(screen.getByRole('button', { name: 'New Revision' }));

      await waitFor(() => {
        expect(screen.getByText('Create New Revision')).toBeInTheDocument();
      });

      const textarea = screen.getByPlaceholderText('Edit content for new revision...');
      fireEvent.change(textarea, { target: { value: 'Test content' } });

      // Click button and press Ctrl+Enter rapidly
      const createBtn = screen.getByRole('button', { name: 'Create Revision' });
      fireEvent.click(createBtn);
      fireEvent.keyDown(textarea, { key: 'Enter', ctrlKey: true });

      // Wait for mutation
      await waitFor(() => {
        expect(mockCreateRevision).toHaveBeenCalledTimes(1);
      });

      // Should only be called once
      expect(mockCreateRevision).toHaveBeenCalledTimes(1);
    }, { timeout: 15000 });

    it('shows loading state on Create Revision button during mutation', async () => {
      let resolveCreateRevision: (value: any) => void;
      const createRevisionPromise = new Promise(resolve => { resolveCreateRevision = resolve; });
      mockCreateRevision.mockReturnValueOnce(createRevisionPromise);

      await renderAndWaitForLoad(<ContentDetail />);

      fireEvent.click(screen.getByRole('button', { name: 'New Revision' }));

      await waitFor(() => {
        expect(screen.getByText('Create New Revision')).toBeInTheDocument();
      });

      const textarea = screen.getByPlaceholderText('Edit content for new revision...');
      fireEvent.change(textarea, { target: { value: 'Test content' } });

      fireEvent.click(screen.getByRole('button', { name: 'Create Revision' }));

      // Button should show loading state - check before resolving the promise
      // The editor's Create Revision button is within the editor dialog
      await waitFor(() => {
        const creatingButtons = screen.getAllByRole('button', { name: 'Creating...' });
        expect(creatingButtons.length).toBeGreaterThanOrEqual(1);
        // At least one should be the editor's Create Revision button
        expect(creatingButtons[0]).toBeInTheDocument();
      });

      // Now resolve the promise
      resolveCreateRevision!({ revision_id: 'revision-2', version: 2 });
      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      // Editor should close
      await waitFor(() => {
        expect(screen.queryByText('Create New Revision')).not.toBeInTheDocument();
      });
    }, { timeout: 15000 });

    it('preserves editor and entered text on mutation failure', async () => {
      mockCreateRevision.mockRejectedValueOnce(new Error('Database error'));

      await renderAndWaitForLoad(<ContentDetail />);

      fireEvent.click(screen.getByRole('button', { name: 'New Revision' }));

      await waitFor(() => {
        expect(screen.getByText('Create New Revision')).toBeInTheDocument();
      });

      const textarea = screen.getByPlaceholderText('Edit content for new revision...');
      fireEvent.change(textarea, { target: { value: 'Failed content' } });

      fireEvent.click(screen.getByRole('button', { name: 'Create Revision' }));

      // Should show error toast
      await waitFor(() => {
        expect(screen.getByText('Database error')).toBeInTheDocument();
      });

      // Editor should remain open with entered text preserved
      expect(screen.getByText('Create New Revision')).toBeInTheDocument();
      expect(textarea).toHaveValue('Failed content');

      // Create Revision button should be enabled again
      expect(screen.getByRole('button', { name: 'Create Revision' })).not.toBeDisabled();
    }, { timeout: 15000 });
  });

  describe('Existing safeguards preserved', () => {
    it('Start Review button is enabled when no review exists', async () => {
      // Remove the default review
      mockGetLatestReviewForRevision.mockResolvedValueOnce(null);

      await renderAndWaitForLoad(<ContentDetail />);

      expect(screen.getByRole('button', { name: 'Start Review' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Start Review' })).not.toBeDisabled();
    }, { timeout: 15000 });

    it('can submit when review has zero findings', async () => {
      // Content has draft status, review is done with zero findings
      await renderAndWaitForLoad(<ContentDetail />);

      const submitButtons = screen.getAllByRole('button', {
        name: 'Submit for Review',
      });

      expect(submitButtons).toHaveLength(2);

      for (const button of submitButtons) {
        expect(button).toBeEnabled();
      }

      expect(
        screen.getByText(
          'No findings were generated. You can submit this content for approval.'
        )
      ).toBeInTheDocument();
    }, { timeout: 15000 });

    it('cannot submit when review has unresolved findings', async () => {
      mockGetFindingsWithDecisionsForReview.mockResolvedValueOnce([
        {
          id: 'finding-1',
          org_id: 'org-1',
          review_id: 'review-1',
          source: 'deterministic',
          rule_id: 'rule-1',
          fact_id: null,
          ref_key: 'TERM-01',
          category: 'terminology',
          severity: 'low',
          quote: 'test',
          start_offset: 0,
          end_offset: 4,
          explanation: 'Test finding',
          suggestion: 'test',
          confidence: null,
          needs_human: false,
          needs_reviewer: false,
          created_at: '2026-01-01T00:00:00Z',
          last_action: null,
          last_reason: null,
          last_edited_text: null,
          resulting_revision_id: null,
          decided_at: null,
        },
      ]);

      await renderAndWaitForLoad(<ContentDetail />);

      // Should show findings
      await waitFor(() => {
        expect(screen.getByText(/Findings \(1\)/)).toBeInTheDocument();
      });

      // Submit button should not be visible (findings not decided)
      expect(screen.queryByRole('button', { name: 'Submit for Review' })).not.toBeInTheDocument();
    }, { timeout: 15000 });

    it('cannot submit when review has pending accept/edit decisions', async () => {
      mockGetFindingsWithDecisionsForReview.mockResolvedValueOnce([
        {
          id: 'finding-1',
          org_id: 'org-1',
          review_id: 'review-1',
          source: 'deterministic',
          rule_id: 'rule-1',
          fact_id: null,
          ref_key: 'TERM-01',
          category: 'terminology',
          severity: 'low',
          quote: 'test',
          start_offset: 0,
          end_offset: 4,
          explanation: 'Test finding',
          suggestion: 'test',
          confidence: null,
          needs_human: false,
          needs_reviewer: false,
          created_at: '2026-01-01T00:00:00Z',
          last_action: 'accept',
          last_reason: null,
          last_edited_text: null,
          resulting_revision_id: null,
          decided_at: '2026-01-01T00:00:00Z',
        },
      ]);

      await renderAndWaitForLoad(<ContentDetail />);

      // Should show pending decisions
      await waitFor(() => {
        expect(screen.getByText(/Pending Decisions/)).toBeInTheDocument();
      });

      // Submit button should not be visible (pending decisions)
      expect(screen.queryByRole('button', { name: 'Submit for Review' })).not.toBeInTheDocument();
    }, { timeout: 15000 });

    it('cannot submit when review failed or unfinished', async () => {
      mockGetLatestReviewForRevision.mockResolvedValue({
        ...defaultReview,
        status: 'running',
      });

      await renderAndWaitForLoad(<ContentDetail />);

      await waitFor(() => {
        expect(screen.getByText(/Review is in progress/)).toBeInTheDocument();
      });

      expect(screen.queryByRole('button', { name: 'Submit for Review' })).not.toBeInTheDocument();
    }, { timeout: 15000 });
  });
});
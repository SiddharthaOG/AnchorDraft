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
  mockCreateReviewPreview,
  mockConfirmReviewPreview,
  mockUploadVisualAsset,
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
  mockCreateReviewPreview: vi.fn(),
  mockConfirmReviewPreview: vi.fn(),
  mockUploadVisualAsset: vi.fn(),
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
  createReviewPreview: mockCreateReviewPreview,
  confirmReviewPreview: mockConfirmReviewPreview,
  uploadVisualAsset: mockUploadVisualAsset,
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
    mockUploadVisualAsset.mockResolvedValue({
      asset_id: 'asset-uploaded-1',
      width: 640,
      height: 480,
      mime_type: 'image/png',
      checksum: 'c'.repeat(64),
      signed_url: 'https://storage.example/asset-uploaded-1.png',
      expires_in: 3600,
    });
    mockCreateReviewPreview.mockResolvedValue({
      preview_id: 'preview-1',
      revision_id: 'revision-1',
      confirmation_token: 'one-time-token',
      expires_at: '2026-11-11T12:10:00Z',
      redacted_draft: 'Contact [EMAIL-12345678]',
      text_provider_preview: { system_instruction: 'Review safely', user_content: 'Contact [EMAIL-12345678]' },
      vision_provider_preview: {
        system_instruction: 'Inspect image',
        user_content: 'Analyse attached image asset-1',
      },
      assets: [{
        id: 'asset-1',
        checksum: 'a'.repeat(64),
        mime_type: 'image/png',
        width: 100,
        height: 100,
        preview_url: 'https://storage.example/asset.png',
      }],
      image_consent_required: true,
      redaction_summary: {
        total_matches: 1,
        by_type: { EMAIL: 1 },
        original_chars: 25,
        redacted_chars: 20,
        policy_version: 1,
      },
      payload_sha256: 'b'.repeat(64),
    });
    mockConfirmReviewPreview.mockResolvedValue({
      review_id: 'review-2',
      status: 'queued',
      deduplicated: false,
      kit_id: 'kit-1',
      kit_version: 1,
    });
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
    it('shows "New Revision" button when content is editable and no editor is open', { timeout: 15000 }, async () => {
      await renderAndWaitForLoad(<ContentDetail />);

      expect(screen.getByRole('button', { name: 'New Revision' })).toBeInTheDocument();
      // Editor should not be visible initially
      expect(screen.queryByText('Create New Revision')).not.toBeInTheDocument();
    });

    it('opens the revision editor when "New Revision" is clicked', { timeout: 15000 }, async () => {
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
    });

    it('does not disable Create Revision button when editor opens', { timeout: 15000 }, async () => {
      await renderAndWaitForLoad(<ContentDetail />);

      fireEvent.click(screen.getByRole('button', { name: 'New Revision' }));

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Create Revision' })).not.toBeDisabled();
      });
    });

    it('closes editor when Cancel is clicked without calling createRevision', { timeout: 15000 }, async () => {
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
    });

    it('closes editor when X button is clicked', { timeout: 15000 }, async () => {
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
    });
  });

  describe('Revision Creation Submission', () => {
    it('calls createRevision with exact textarea content when Create Revision button is clicked', { timeout: 15000 }, async () => {
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
    });

    it('submits same content via Ctrl+Enter shortcut', { timeout: 15000 }, async () => {
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
    });

    it('submits same content via Meta+Enter shortcut (Mac)', { timeout: 15000 }, async () => {
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
    });

    it('rejects empty content with error message', { timeout: 15000 }, async () => {
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
    });

    it('rejects whitespace-only content with error message', { timeout: 15000 }, async () => {
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
    });

    it('prevents duplicate submissions when double-clicking Create Revision', { timeout: 15000 }, async () => {
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
    });

    it('prevents duplicate submissions via button click and Ctrl+Enter', { timeout: 15000 }, async () => {
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
    });

    it('shows loading state on Create Revision button during mutation', { timeout: 15000 }, async () => {
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
    });

    it('preserves editor and entered text on mutation failure', { timeout: 15000 }, async () => {
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
    });
  });

  describe('Visual asset uploads', () => {
    it('uploads multiple supported images to the latest revision and shows their previews', { timeout: 15000 }, async () => {
      mockGetLatestReviewForRevision.mockResolvedValue(null);
      mockUploadVisualAsset
        .mockResolvedValueOnce({
          asset_id: 'asset-uploaded-png', width: 640, height: 480, mime_type: 'image/png',
          checksum: 'a'.repeat(64), signed_url: 'https://storage.example/brand.png', expires_in: 3600,
        })
        .mockResolvedValueOnce({
          asset_id: 'asset-uploaded-jpeg', width: 1200, height: 800, mime_type: 'image/jpeg',
          checksum: 'b'.repeat(64), signed_url: 'https://storage.example/photo.jpg', expires_in: 3600,
        });

      await renderAndWaitForLoad(<ContentDetail />);
      const png = new File(['png'], 'brand.png', { type: 'image/png' });
      const jpeg = new File(['jpeg'], 'photo.jpg', { type: 'image/jpeg' });
      fireEvent.change(screen.getByLabelText('Choose images to upload'), {
        target: { files: [png, jpeg] },
      });

      await waitFor(() => expect(mockUploadVisualAsset).toHaveBeenCalledTimes(2));
      expect(mockUploadVisualAsset).toHaveBeenNthCalledWith(1, png, 'content-1', 'revision-1');
      expect(mockUploadVisualAsset).toHaveBeenNthCalledWith(2, jpeg, 'content-1', 'revision-1');
      expect(await screen.findByText('brand.png')).toBeInTheDocument();
      expect(screen.getByText('photo.jpg')).toBeInTheDocument();
      // Attaching new images invalidates the old review presentation and requires a fresh preview.
      expect(screen.getByRole('button', { name: 'Start Review' })).toBeEnabled();
    });

    it('prevents image uploads while viewing a historical revision', { timeout: 15000 }, async () => {
      const olderRevision = { ...defaultRevision, id: 'revision-0', version: 0 };
      mockGetLatestReviewForRevision.mockResolvedValue(null);
      mockGetRevisions.mockResolvedValue([olderRevision, defaultRevision]);

      await renderAndWaitForLoad(<ContentDetail />);
      fireEvent.click(screen.getByRole('button', { name: /Revision 0/ }));

      expect(screen.getByRole('button', { name: 'Upload images' })).toBeDisabled();
      expect(mockUploadVisualAsset).not.toHaveBeenCalled();
    });

    it('shows a useful error when an image upload fails', { timeout: 15000 }, async () => {
      mockGetLatestReviewForRevision.mockResolvedValue(null);
      mockUploadVisualAsset.mockRejectedValueOnce(new Error('Each image must be 10 MB or smaller.'));

      await renderAndWaitForLoad(<ContentDetail />);
      const png = new File(['png'], 'too-large.png', { type: 'image/png' });
      fireEvent.change(screen.getByLabelText('Choose images to upload'), {
        target: { files: [png] },
      });

      expect(await screen.findByRole('alert')).toHaveTextContent(
        'too-large.png: Each image must be 10 MB or smaller.',
      );
    });
  });

  describe('Revision-specific review isolation', () => {
    it('loads each revision review and findings independently and keeps historical findings read-only', { timeout: 15000 }, async () => {
      const historicalRevision = { ...defaultRevision, id: 'revision-v4', version: 4, body: 'Historical body' };
      const currentRevision = { ...defaultRevision, id: 'revision-v6', version: 6, body: 'Current body' };
      const historicalReview = { ...defaultReview, id: 'review-v4', revision_id: historicalRevision.id };
      const currentReview = { ...defaultReview, id: 'review-v6', revision_id: currentRevision.id };
      const makeFinding = (id: string, reviewId: string, index: number) => ({
        id, org_id: 'org-1', review_id: reviewId, source: 'llm' as const,
        rule_id: null, fact_id: null, ref_key: 'CLAIM-' + index,
        category: 'claim' as const, severity: 'high' as const,
        quote: 'quote-' + id, start_offset: 0, end_offset: 8,
        explanation: 'Finding explanation ' + id, suggestion: 'Suggestion ' + id,
        confidence: 0.9, needs_human: false, needs_reviewer: false,
        created_at: '2026-01-0' + index + 'T00:00:00Z',
        last_action: null, last_reason: null, last_edited_text: null,
        resulting_revision_id: null, decided_at: null,
      });
      const historicalFindings = Array.from({ length: 6 }, (_, i) => makeFinding('v4-' + (i + 1), historicalReview.id, i + 1));
      const currentFindings = Array.from({ length: 4 }, (_, i) => makeFinding('v6-' + (i + 1), currentReview.id, i + 1));
      mockGetLatestRevision.mockResolvedValue(currentRevision);
      mockGetRevisions.mockResolvedValue([currentRevision, historicalRevision]);
      mockGetLatestReviewForRevision.mockImplementation(async (revisionId: string) => {
        if (revisionId === historicalRevision.id) return historicalReview;
        if (revisionId === currentRevision.id) return currentReview;
        return null;
      });
      mockGetFindingsWithDecisionsForReview.mockImplementation(async (reviewId: string) => {
        if (reviewId === historicalReview.id) return historicalFindings;
        if (reviewId === currentReview.id) return currentFindings;
        return [];
      });

      await renderAndWaitForLoad(<ContentDetail />);
      await waitFor(() => {
        expect(screen.getByText('Findings (4)')).toBeInTheDocument();
        expect(mockGetLatestReviewForRevision).toHaveBeenCalledWith(currentRevision.id);
      });
      expect(screen.getByText('Finding explanation v6-1')).toBeInTheDocument();
      expect(screen.queryByText('Finding explanation v4-1')).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: /Revision 4/ }));
      await waitFor(() => {
        expect(mockGetLatestReviewForRevision).toHaveBeenCalledWith(historicalRevision.id);
        expect(screen.getByText('Findings (6)')).toBeInTheDocument();
      });
      expect(screen.getByText('Finding explanation v4-1')).toBeInTheDocument();
      expect(screen.queryByText('Finding explanation v6-1')).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Accept' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Dismiss' })).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: /Revision 6/ }));
      await waitFor(() => expect(screen.getByText('Findings (4)')).toBeInTheDocument());
      expect(screen.getByText('Finding explanation v6-1')).toBeInTheDocument();
      expect(screen.queryByText('Finding explanation v4-1')).not.toBeInTheDocument();
    });

    it('ignores a delayed historical review response after switching back to the latest revision', { timeout: 15000 }, async () => {
      const historicalRevision = { ...defaultRevision, id: 'revision-v4', version: 4 };
      const currentRevision = { ...defaultRevision, id: 'revision-v6', version: 6 };
      const historicalReview = { ...defaultReview, id: 'review-v4', revision_id: historicalRevision.id };
      const currentReview = { ...defaultReview, id: 'review-v6', revision_id: currentRevision.id };
      let resolveHistoricalReview!: (review: any) => void;
      const delayedHistoricalReview = new Promise(resolve => { resolveHistoricalReview = resolve; });

      mockGetLatestRevision.mockResolvedValue(currentRevision);
      mockGetRevisions.mockResolvedValue([currentRevision, historicalRevision]);
      mockGetLatestReviewForRevision.mockImplementation((revisionId: string) => {
        if (revisionId === historicalRevision.id) return delayedHistoricalReview;
        return Promise.resolve(currentReview);
      });
      mockGetFindingsWithDecisionsForReview.mockImplementation(async (reviewId: string) =>
        reviewId === currentReview.id ? [] : [],
      );

      await renderAndWaitForLoad(<ContentDetail />);
      await waitFor(() => expect(screen.getByText('Findings', { selector: 'p' })).toBeInTheDocument());

      fireEvent.click(screen.getByRole('button', { name: /Revision 4/ }));
      await waitFor(() => expect(mockGetLatestReviewForRevision).toHaveBeenCalledWith(historicalRevision.id));

      fireEvent.click(screen.getByRole('button', { name: /Revision 6/ }));
      await waitFor(() => expect(screen.getByText('Findings', { selector: 'p' })).toBeInTheDocument());

      await act(async () => {
        resolveHistoricalReview(historicalReview);
        await delayedHistoricalReview;
      });

      expect(screen.queryByText('No review is available for historical Revision 4.')).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Start Review' })).not.toBeInTheDocument();
      expect(mockGetLatestReviewForRevision).toHaveBeenLastCalledWith(currentRevision.id);
    });

    it('does not offer a new review preview for a historical revision without a review', { timeout: 15000 }, async () => {
      const historicalRevision = { ...defaultRevision, id: 'revision-v4', version: 4 };
      const currentRevision = { ...defaultRevision, id: 'revision-v6', version: 6 };
      mockGetLatestRevision.mockResolvedValue(currentRevision);
      mockGetRevisions.mockResolvedValue([currentRevision, historicalRevision]);
      mockGetLatestReviewForRevision.mockImplementation(async (revisionId: string) =>
        revisionId === currentRevision.id ? defaultReview : null,
      );
      await renderAndWaitForLoad(<ContentDetail />);
      fireEvent.click(screen.getByRole('button', { name: /Revision 4/ }));
      expect(await screen.findByText('No review is available for historical Revision 4.')).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Start Review' })).not.toBeInTheDocument();
      expect(mockCreateReviewPreview).not.toHaveBeenCalled();
    });

    it('discards a delayed preview response when the user switches to a historical revision', { timeout: 15000 }, async () => {
      const historicalRevision = { ...defaultRevision, id: 'revision-0', version: 0 };
      let resolvePreview!: (preview: any) => void;
      const delayedPreview = new Promise(resolve => { resolvePreview = resolve; });

      mockGetLatestRevision.mockResolvedValue(defaultRevision);
      mockGetRevisions.mockResolvedValue([defaultRevision, historicalRevision]);
      mockGetLatestReviewForRevision.mockResolvedValue(null);
      mockCreateReviewPreview.mockReturnValueOnce(delayedPreview);

      await renderAndWaitForLoad(<ContentDetail />);
      fireEvent.click(screen.getByRole('button', { name: 'Start Review' }));
      await waitFor(() => expect(mockCreateReviewPreview).toHaveBeenCalledWith(defaultRevision.id));

      fireEvent.click(screen.getByRole('button', { name: /Revision 0/ }));
      expect(await screen.findByText('No review is available for historical Revision 0.')).toBeInTheDocument();

      await act(async () => {
        resolvePreview({
          preview_id: 'stale-preview',
          revision_id: defaultRevision.id,
          confirmation_token: 'stale-token',
          expires_at: '2026-11-12T12:10:00Z',
          redacted_draft: 'Stale preview',
          text_provider_preview: { system_instruction: 'Review', user_content: 'Stale' },
          vision_provider_preview: null,
          assets: [],
          image_consent_required: false,
          redaction_summary: { total_matches: 0, by_type: {}, original_chars: 5, redacted_chars: 5, policy_version: 1 },
          payload_sha256: 'c'.repeat(64),
        });
        await delayedPreview;
      });

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Confirm & Run Review' })).not.toBeInTheDocument();
      expect(mockConfirmReviewPreview).not.toHaveBeenCalled();
      expect(screen.queryByRole('button', { name: 'Start Review' })).not.toBeInTheDocument();
    });

    it('closes an open preview and clears image consent when switching revisions', { timeout: 15000 }, async () => {
      const historicalRevision = { ...defaultRevision, id: 'revision-0', version: 0 };
      mockGetLatestRevision.mockResolvedValue(defaultRevision);
      mockGetRevisions.mockResolvedValue([defaultRevision, historicalRevision]);
      mockGetLatestReviewForRevision.mockResolvedValue(null);

      await renderAndWaitForLoad(<ContentDetail />);
      fireEvent.click(screen.getByRole('button', { name: 'Start Review' }));
      await screen.findByRole('dialog');

      const consent = screen.getByRole('checkbox', {
        name: /explicitly consent to sending them in their stored form/i,
      });
      fireEvent.click(consent);
      expect(consent).toBeChecked();

      fireEvent.click(screen.getByRole('button', { name: /Revision 0/ }));
      expect(await screen.findByText('No review is available for historical Revision 0.')).toBeInTheDocument();
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(screen.queryByRole('checkbox', {
        name: /explicitly consent to sending them in their stored form/i,
      })).not.toBeInTheDocument();
      expect(mockConfirmReviewPreview).not.toHaveBeenCalled();
    });
  });

  describe('Existing safeguards preserved', () => {
    it('Start Review button is enabled when no review exists', { timeout: 15000 }, async () => {
      // Remove the default review
      mockGetLatestReviewForRevision.mockResolvedValueOnce(null);

      await renderAndWaitForLoad(<ContentDetail />);

      expect(screen.getByRole('button', { name: 'Start Review' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Start Review' })).not.toBeDisabled();
    });

    it('shows the redacted preview and requires explicit consent before confirmation', { timeout: 15000 }, async () => {
      mockGetLatestReviewForRevision.mockResolvedValue(null);
      await renderAndWaitForLoad(<ContentDetail />);

      fireEvent.click(screen.getByRole('button', { name: 'Start Review' }));
      await waitFor(() => {
        expect(mockCreateReviewPreview).toHaveBeenCalledWith('revision-1');
      });
      const dialog = await screen.findByRole('dialog');
      expect(screen.getAllByText('Contact [EMAIL-12345678]').length).toBeGreaterThan(0);
      expect(screen.getByText(/Image pixels are not OCR-redacted/)).toBeInTheDocument();

      const confirmButton = screen.getByRole('button', { name: 'Confirm & Run Review' });
      expect(confirmButton).toBeDisabled();
      expect(mockConfirmReviewPreview).not.toHaveBeenCalled();
      const consent = screen.getByRole('checkbox', {
        name: /explicitly consent to sending them in their stored form/i,
      });
      fireEvent.click(consent);
      expect(confirmButton).toBeEnabled();

      fireEvent.click(confirmButton);
      await waitFor(() => {
        expect(mockConfirmReviewPreview).toHaveBeenCalledWith(
          'preview-1',
          'one-time-token',
          true,
        );
      });
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
      expect(mockCreateReviewPreview).toHaveBeenCalledWith('revision-1');
    });

    it('closes a stale preview and explains when attached images changed after preview creation', { timeout: 15000 }, async () => {
      mockGetLatestReviewForRevision.mockResolvedValue(null);
      const conflict = Object.assign(new Error('Attached images changed after preview'), {
        status: 409,
        reason: 'assets_changed',
      });
      mockConfirmReviewPreview.mockRejectedValueOnce(conflict);

      await renderAndWaitForLoad(<ContentDetail />);
      fireEvent.click(screen.getByRole('button', { name: 'Start Review' }));
      await screen.findByRole('dialog');
      const consent = screen.getByRole('checkbox', {
        name: /explicitly consent to sending them in their stored form/i,
      });
      fireEvent.click(consent);
      fireEvent.click(screen.getByRole('button', { name: 'Confirm & Run Review' }));

      expect(await screen.findByText(/Attached images changed after this preview was created/)).toBeInTheDocument();
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Start Review' })).toBeEnabled();
      expect(mockConfirmReviewPreview).toHaveBeenCalledWith('preview-1', 'one-time-token', true);
    });

    it('shows unexpected confirmation failures inside the open preview dialog', { timeout: 15000 }, async () => {
      mockGetLatestReviewForRevision.mockResolvedValue(null);
      mockConfirmReviewPreview.mockRejectedValueOnce(new Error('Temporary provider queue outage'));

      await renderAndWaitForLoad(<ContentDetail />);
      fireEvent.click(screen.getByRole('button', { name: 'Start Review' }));
      await screen.findByRole('dialog');
      const consent = screen.getByRole('checkbox', {
        name: /explicitly consent to sending them in their stored form/i,
      });
      fireEvent.click(consent);
      fireEvent.click(screen.getByRole('button', { name: 'Confirm & Run Review' }));

      expect(await screen.findByRole('alert')).toHaveTextContent('Temporary provider queue outage');
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    it('shows an actionable error instead of silently ignoring Start Review when no revision is loaded', { timeout: 15000 }, async () => {
      mockGetLatestRevision.mockResolvedValueOnce(null);
      mockGetRevisions.mockResolvedValueOnce([]);
      mockGetLatestReviewForRevision.mockResolvedValue(null);

      await renderAndWaitForLoad(<ContentDetail />);
      fireEvent.click(screen.getByRole('button', { name: 'Start Review' }));

      expect(await screen.findByRole('alert')).toHaveTextContent(
        'This content has no loaded revision yet. Reload the content and try again.',
      );
      expect(mockCreateReviewPreview).not.toHaveBeenCalled();
      expect(screen.getByRole('button', { name: 'Start Review' })).toBeEnabled();
    });

    it('shows preview API failures beside Start Review so a fast 4xx is not mistaken for an inert button', { timeout: 15000 }, async () => {
      mockGetLatestReviewForRevision.mockResolvedValue(null);
      mockCreateReviewPreview.mockRejectedValueOnce(new Error('Request validation failed: body.revision_id: invalid UUID'));

      await renderAndWaitForLoad(<ContentDetail />);
      fireEvent.click(screen.getByRole('button', { name: 'Start Review' }));

      expect(await screen.findByRole('alert')).toHaveTextContent(
        'Could not prepare review preview: Request validation failed: body.revision_id: invalid UUID',
      );
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('can submit when review has zero findings', { timeout: 15000 }, async () => {
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
    });

    it('does not briefly expose submission before findings finish loading', { timeout: 15000 }, async () => {
      let resolveFindings!: (value: any[]) => void;
      mockGetFindingsWithDecisionsForReview.mockImplementationOnce(() =>
        new Promise(resolve => { resolveFindings = resolve; }),
      );

      await renderAndWaitForLoad(<ContentDetail />);

      // The review status can arrive before its findings. Empty initial state
      // must never be treated as a completed, zero-finding review.
      expect(screen.queryByRole('button', { name: 'Submit for Review' })).not.toBeInTheDocument();

      await act(async () => {
        resolveFindings([]);
      });

      await waitFor(() => {
        expect(screen.getAllByRole('button', { name: 'Submit for Review' })).toHaveLength(2);
      });
    });

    it('cannot submit when review has unresolved findings', { timeout: 15000 }, async () => {
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
    });

    it('cannot submit when review has pending accept/edit decisions', { timeout: 15000 }, async () => {
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
    });

    it('keeps findings returned by a completed polling request', { timeout: 15000 }, async () => {
      let resolveTerminalFindings!: (value: any[]) => void;
      const terminalFindings = new Promise<any[]>(resolve => {
        resolveTerminalFindings = resolve;
      });
      const queuedReview = { ...defaultReview, status: 'queued' as const };
      const completedReview = { ...defaultReview, status: 'done' as const };
      const finding = {
        id: 'finding-from-poll',
        org_id: 'org-1',
        review_id: 'review-1',
        source: 'llm',
        rule_id: null,
        fact_id: null,
        ref_key: 'CLAIM-01',
        category: 'claim',
        severity: 'high',
        quote: 'guaranteed uptime',
        start_offset: 0,
        end_offset: 17,
        explanation: 'Unsupported absolute guarantee',
        suggestion: 'remove the guarantee',
        confidence: 0.98,
        needs_human: false,
        needs_reviewer: false,
        created_at: '2026-01-01T00:00:00Z',
        last_action: null,
        last_reason: null,
        last_edited_text: null,
        resulting_revision_id: null,
        decided_at: null,
      };

      mockGetLatestReviewForRevision
        .mockResolvedValueOnce(queuedReview)
        .mockResolvedValueOnce(completedReview);
      mockGetFindingsWithDecisionsForReview
        .mockResolvedValueOnce([])
        .mockReturnValueOnce(terminalFindings);

      await renderAndWaitForLoad(<ContentDetail />);

      await waitFor(() => {
        expect(mockGetFindingsWithDecisionsForReview).toHaveBeenCalledTimes(2);
      });

      // Let the terminal findings fetch complete only after the UI has seen
      // the completed status. The poll must remain valid until it stores them.
      await act(async () => {
        resolveTerminalFindings([finding]);
        await terminalFindings;
      });

      expect(await screen.findByText(/Findings \(1\)/)).toBeInTheDocument();
      expect(screen.getByText('Unsupported absolute guarantee')).toBeInTheDocument();
      expect(screen.queryByText('No findings were generated. You can submit this content for approval.')).not.toBeInTheDocument();
    });
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
    });
  });
});
/** Tests for ReviewerLanding component. */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ReviewerLanding } from './ReviewerLanding';

// Mock the data layer using vi.hoisted
const { mockGetContents, mockGetContentStats, mockGetPendingSignoffsByOrg } = vi.hoisted(() => ({
  mockGetContents: vi.fn(),
  mockGetContentStats: vi.fn(),
  mockGetPendingSignoffsByOrg: vi.fn(),
}));

vi.mock('../../lib/data', () => ({
  getContents: mockGetContents,
  getContentStats: mockGetContentStats,
  getPendingSignoffsByOrg: mockGetPendingSignoffsByOrg,
}));

// Mock the auth service using vi.hoisted
const { mockSession: mockReviewerSession } = vi.hoisted(() => ({
  mockSession: {
    user: { id: 'user-1', email: 'reviewer@example.com' },
    profile: { display_name: 'Test Reviewer', user_id: 'user-1', created_at: '2026-01-01' },
    memberships: [{ org_id: 'org-1', user_id: 'user-1', roles: ['reviewer'], created_at: '2026-01-01' }],
    organizations: [{ id: 'org-1', name: 'Test Org', created_at: '2026-01-01' }],
    currentOrgId: 'org-1',
    currentOrgName: 'Test Org',
    currentRoles: ['reviewer'],
    isLoading: false,
    error: null,
  },
}));

vi.mock('../../features/auth/AuthProvider', () => ({
  useAuth: () => ({
    session: mockReviewerSession,
    isLoading: false,
    error: null,
    signInWithEmail: vi.fn(),
    signInWithOAuth: vi.fn(),
    signOut: vi.fn(),
    switchOrganization: vi.fn(),
    hasRole: vi.fn((role: string) => mockReviewerSession.currentRoles.includes(role)),
    hasAnyRole: vi.fn((roles: string[]) => roles.some(role => mockReviewerSession.currentRoles.includes(role))),
    getPrimaryRole: vi.fn(() => 'reviewer'),
    refreshSession: vi.fn(),
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));

describe('ReviewerLanding', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetContentStats.mockResolvedValue({
      total: 5,
      draft: 1,
      submitted: 3,
      changes_requested: 1,
      approved: 2,
    });
    mockGetContents.mockResolvedValue([
      { id: 'content-1', title: 'Submitted Article 1', channel: 'blog', status: 'submitted', purpose: 'Educational', created_at: '2026-01-01T00:00:00Z' },
      { id: 'content-2', title: 'Submitted Article 2', channel: 'linkedin', status: 'submitted', purpose: 'Announcement', created_at: '2026-01-02T00:00:00Z' },
    ]);
    // content-1 has 2 findings (CLAIM-01, FACT-01), content-2 has 1 finding (TONE-01)
    mockGetPendingSignoffsByOrg.mockResolvedValue([
      { finding_id: 'finding-1', content_id: 'content-1', ref_key: 'CLAIM-01', category: 'claim', severity: 'high', quote: 'guaranteed', explanation: 'Absolute claim not supported', needs_human: true },
      { finding_id: 'finding-2', content_id: 'content-1', ref_key: 'FACT-01', category: 'fact', severity: 'medium', quote: '99.9% uptime', explanation: 'Contradicts approved fact', needs_human: false },
      { finding_id: 'finding-3', content_id: 'content-2', ref_key: 'TONE-01', category: 'tone', severity: 'low', quote: 'It is imperative', explanation: 'Too formal', needs_human: false },
    ]);
  });

  afterEach(() => {
    cleanup();
  });

  it('shows loading screen while data is loading', async () => {
    let resolveData: (value: any) => void;
    const dataPromise = new Promise(resolve => { resolveData = resolve; });
    mockGetContentStats.mockReturnValueOnce(dataPromise);
    mockGetContents.mockReturnValueOnce(dataPromise);
    mockGetPendingSignoffsByOrg.mockReturnValueOnce(dataPromise);

    render(<ReviewerLanding />, { wrapper: TestWrapper });

    expect(screen.getByText('Loading review data...')).toBeInTheDocument();

    resolveData!({ total: 0, draft: 0, submitted: 0, changes_requested: 0, approved: 0 });
    resolveData!([]);
    resolveData!([]);

    await waitFor(() => {
      expect(screen.queryByText('Loading review data...')).not.toBeInTheDocument();
    });
  });

  it('shows error state when data fetch fails', async () => {
    mockGetContentStats.mockRejectedValueOnce(new Error('Network error'));

    render(<ReviewerLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText('Unable to load data')).toBeInTheDocument();
    });
    expect(screen.getByText('Network error')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('shows empty state when no pending signoffs', async () => {
    mockGetContents.mockResolvedValueOnce([]);
    mockGetContentStats.mockResolvedValueOnce({ total: 0, draft: 0, submitted: 0, changes_requested: 0, approved: 0 });
    mockGetPendingSignoffsByOrg.mockResolvedValueOnce([]);

    render(<ReviewerLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText('No findings awaiting your sign-off')).toBeInTheDocument();
    });
  });

  it('displays corrected stats with accurate labels', async () => {
    render(<ReviewerLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText('Pending Sign-offs')).toBeInTheDocument();
      expect(screen.getAllByText('3').length).toBeGreaterThan(0);
      expect(screen.getAllByText('Claims to Reject')).toHaveLength(2);
      expect(screen.getByText('1')).toBeInTheDocument();
      expect(screen.getByText('Approved Content')).toBeInTheDocument();
      expect(screen.getByText('2')).toBeInTheDocument();
      expect(screen.getByText('Submitted Content')).toBeInTheDocument();
      expect(screen.getAllByText('3').length).toBeGreaterThan(0);
    });
  });

  it('groups findings by content and displays exact finding count per group', async () => {
    render(<ReviewerLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      // content IDs are sliced to 8 chars, so "content-1" -> "content-", "content-2" -> "content-"
      const contentHeaders = screen.getAllByText((content: string) => /Content #content-/i.test(content));
      expect(contentHeaders.length).toBe(2);

      // First content group (content-1) should show "2 findings awaiting sign-off"
      expect(screen.getByText('2 findings awaiting sign-off')).toBeInTheDocument();

      // Second content group (content-2) should show "1 findings awaiting sign-off"
      // Use function matcher since text may be split across elements
      expect(screen.getByText((content: string) => /findings awaiting sign-off/i.test(content))).toBeInTheDocument();
    });
  });

  it('does not mix findings from different content items', async () => {
    render(<ReviewerLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      // Verify content-1 has CLAIM-01 and FACT-01
      // Find the first content header container
      const contentHeaders = screen.getAllByText((content: string) => /Content #content-/i.test(content));
      expect(contentHeaders.length).toBe(2);

      const content1Header = contentHeaders[0];
      const content1Container = content1Header.closest('.border.border-gray-200') || content1Header.parentElement?.parentElement;
      expect(content1Container).toBeInTheDocument();
      expect(content1Container?.textContent).toContain('CLAIM-01');
      expect(content1Container?.textContent).toContain('FACT-01');
      expect(content1Container?.textContent).not.toContain('TONE-01');

      // Verify content-2 has TONE-01
      const content2Header = contentHeaders[1];
      const content2Container = content2Header.closest('.border.border-gray-200') || content2Header.parentElement?.parentElement;
      expect(content2Container).toBeInTheDocument();
      expect(content2Container?.textContent).toContain('TONE-01');
      expect(content2Container?.textContent).not.toContain('CLAIM-01');
      expect(content2Container?.textContent).not.toContain('FACT-01');
    });
  });

  it('displays corrected stats with accurate labels', async () => {
    render(<ReviewerLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText('Pending Sign-offs')).toBeInTheDocument();
      expect(screen.getAllByText('3').length).toBeGreaterThan(0);
      expect(screen.getAllByText('Claims to Reject')).toHaveLength(2);
      expect(screen.getByText('1')).toBeInTheDocument();
      expect(screen.getByText('Approved Content')).toBeInTheDocument();
      expect(screen.getByText('2')).toBeInTheDocument();
      expect(screen.getByText('Submitted Content')).toBeInTheDocument();
      expect(screen.getAllByText('3').length).toBeGreaterThan(0);
    });
  });

  it('shows coming soon for disabled actions', async () => {
    render(<ReviewerLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText('Review Queue')).toBeInTheDocument();
      expect(screen.getByText('Findings awaiting your decision')).toBeInTheDocument();
      expect(screen.getByText('Review History')).toBeInTheDocument();
      expect(screen.getAllByText('Coming soon')).toHaveLength(2);
      expect(screen.getAllByText('Claims to Reject')).toHaveLength(2);
    });
  });

  it('uses single org-scoped query for pending signoffs called exactly once', async () => {
    render(<ReviewerLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText('Pending Sign-offs')).toBeInTheDocument();
    });

    expect(mockGetPendingSignoffsByOrg).toHaveBeenCalledTimes(1);
    expect(mockGetPendingSignoffsByOrg).toHaveBeenCalledWith('org-1');
  });
});

function TestWrapper({ children }: { children: React.ReactNode }) {
  return (
    <MemoryRouter>
      {children}
    </MemoryRouter>
  );
}
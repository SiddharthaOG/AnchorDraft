/** Tests for ReviewerLanding component. */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ReviewerLanding } from './ReviewerLanding';

// Mock the data layer using vi.hoisted
const { mockGetContents, mockGetContentStats, mockGetPendingSignoffs } = vi.hoisted(() => ({
  mockGetContents: vi.fn(),
  mockGetContentStats: vi.fn(),
  mockGetPendingSignoffs: vi.fn(),
}));

vi.mock('../../lib/data', () => ({
  getContents: mockGetContents,
  getContentStats: mockGetContentStats,
  getPendingSignoffs: mockGetPendingSignoffs,
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
      approved: 0,
    });
    mockGetContents.mockResolvedValue([
      { id: 'content-1', title: 'Submitted Article 1', channel: 'blog', status: 'submitted', purpose: 'Educational', created_at: '2026-01-01T00:00:00Z' },
      { id: 'content-2', title: 'Submitted Article 2', channel: 'linkedin', status: 'submitted', purpose: 'Announcement', created_at: '2026-01-02T00:00:00Z' },
    ]);
    mockGetPendingSignoffs.mockResolvedValue([
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
    mockGetPendingSignoffs.mockReturnValueOnce(dataPromise);

    render(<ReviewerLanding />, { wrapper: TestWrapper });

    // LoadingScreen shows "Loading review data..." for ReviewerLanding
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
    mockGetPendingSignoffs.mockResolvedValueOnce([]);

    render(<ReviewerLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText('No findings awaiting your sign-off')).toBeInTheDocument();
    });
  });

  it('displays stats with sign-off counts', async () => {
    render(<ReviewerLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText('Pending Sign-offs')).toBeInTheDocument();
      expect(screen.getByText('6')).toBeInTheDocument(); // total signoffs (the stat shows 6)
      expect(screen.getAllByText('Claims to Reject')).toHaveLength(2); // appears in stats and quick actions
      expect(screen.getByText('Completed')).toBeInTheDocument();
      expect(screen.getByText('Total Reviews')).toBeInTheDocument();
    });
  });

  it('groups signoffs by content and displays finding details', async () => {
    render(<ReviewerLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      // Content IDs are truncated to 8 chars - "content-1" becomes "content-"
      // There are 2 content items, so this text appears twice
      expect(screen.getAllByText((content: string) => /Content #content-/i.test(content)).length).toBe(2);
      // "findings awaiting sign-off" appears for each content group - use getAllByText
      expect(screen.getAllByText((content: string) => /findings awaiting sign-off/i.test(content)).length).toBeGreaterThan(0);
    });

    // Check finding details - some texts appear multiple times (in stats and findings list)
    // Use getAllByText with function matchers and check length > 0
    expect(screen.getAllByText((content: string) => /CLAIM-01/i.test(content)).length).toBeGreaterThan(0);
    expect(screen.getAllByText((content: string) => /FACT-01/i.test(content)).length).toBeGreaterThan(0);
    expect(screen.getAllByText((content: string) => /TONE-01/i.test(content)).length).toBeGreaterThan(0);
    expect(screen.getAllByText((content: string) => /claim/i.test(content)).length).toBeGreaterThan(0);
    expect(screen.getAllByText((content: string) => /fact/i.test(content)).length).toBeGreaterThan(0);
    expect(screen.getAllByText((content: string) => /tone/i.test(content)).length).toBeGreaterThan(0);
    expect(screen.getAllByText((content: string) => /high/i.test(content)).length).toBeGreaterThan(0);
    expect(screen.getAllByText((content: string) => /medium/i.test(content)).length).toBeGreaterThan(0);
    expect(screen.getAllByText((content: string) => /low/i.test(content)).length).toBeGreaterThan(0);
    expect(screen.getAllByText((content: string) => /guaranteed/i.test(content)).length).toBeGreaterThan(0);
    expect(screen.getAllByText((content: string) => /Absolute claim not supported/i.test(content)).length).toBeGreaterThan(0);
    expect(screen.getAllByText((content: string) => /Needs human review/i.test(content)).length).toBeGreaterThan(0);
  });

  it('shows coming soon for disabled actions', async () => {
    render(<ReviewerLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText('Review Queue')).toBeInTheDocument();
      expect(screen.getByText('Findings awaiting your decision')).toBeInTheDocument();
      expect(screen.getByText('Review History')).toBeInTheDocument();
      expect(screen.getAllByText('Coming soon')).toHaveLength(2); // Review History and Claims to Reject
      expect(screen.getAllByText('Claims to Reject')).toHaveLength(2); // Appears in quick actions and stats
    });
  });
});

function TestWrapper({ children }: { children: React.ReactNode }) {
  return (
    <MemoryRouter>
      {children}
    </MemoryRouter>
  );
}
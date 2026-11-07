/** Tests for ManagerLanding component. */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ManagerLanding } from './ManagerLanding';

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
const { mockSession: mockManagerSession } = vi.hoisted(() => ({
  mockSession: {
    user: { id: 'user-1', email: 'manager@example.com' },
    profile: { display_name: 'Test Manager', user_id: 'user-1', created_at: '2026-01-01' },
    memberships: [{ org_id: 'org-1', user_id: 'user-1', roles: ['manager'], created_at: '2026-01-01' }],
    organizations: [{ id: 'org-1', name: 'Test Org', created_at: '2026-01-01' }],
    currentOrgId: 'org-1',
    currentOrgName: 'Test Org',
    currentRoles: ['manager'],
    isLoading: false,
    error: null,
  },
}));

vi.mock('../../features/auth/AuthProvider', () => ({
  useAuth: () => ({
    session: mockManagerSession,
    isLoading: false,
    error: null,
    signInWithEmail: vi.fn(),
    signInWithOAuth: vi.fn(),
    signOut: vi.fn(),
    switchOrganization: vi.fn(),
    hasRole: vi.fn((role: string) => mockManagerSession.currentRoles.includes(role)),
    hasAnyRole: vi.fn((roles: string[]) => roles.some(role => mockManagerSession.currentRoles.includes(role))),
    getPrimaryRole: vi.fn(() => 'manager'),
    refreshSession: vi.fn(),
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));

describe('ManagerLanding', () => {
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
      { id: 'content-3', title: 'Submitted Article 3', channel: 'website', status: 'submitted', purpose: 'Documentation', created_at: '2026-01-03T00:00:00Z' },
    ]);
    mockGetPendingSignoffs.mockResolvedValue([
      { finding_id: 'finding-1', content_id: 'content-1', ref_key: 'CLAIM-01', category: 'claim', severity: 'high', quote: 'guaranteed', explanation: 'Absolute claim', needs_human: true },
      { finding_id: 'finding-2', content_id: 'content-2', ref_key: 'CLAIM-02', category: 'claim', severity: 'high', quote: 'best in class', explanation: 'Unsupported superiority', needs_human: false },
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

    render(<ManagerLanding />, { wrapper: TestWrapper });

    // LoadingScreen shows "Loading approval data..." for ManagerLanding
    expect(screen.getByText('Loading approval data...')).toBeInTheDocument();

    resolveData!({ total: 0, draft: 0, submitted: 0, changes_requested: 0, approved: 0 });
    resolveData!([]);
    resolveData!([]);

    await waitFor(() => {
      expect(screen.queryByText('Loading approval data...')).not.toBeInTheDocument();
    });
  });

  it('shows error state when data fetch fails', async () => {
    mockGetContentStats.mockRejectedValueOnce(new Error('Network error'));

    render(<ManagerLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText('Unable to load data')).toBeInTheDocument();
    });
    expect(screen.getByText('Network error')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('shows empty state when no submitted content', async () => {
    mockGetContents.mockResolvedValueOnce([]);
    mockGetContentStats.mockResolvedValueOnce({ total: 0, draft: 0, submitted: 0, changes_requested: 0, approved: 0 });
    mockGetPendingSignoffs.mockResolvedValueOnce([]);

    render(<ManagerLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText('No content submitted for review')).toBeInTheDocument();
    });
  });

  it('displays stats including pending sign-offs', async () => {
    render(<ManagerLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getAllByText('Submitted')).toHaveLength(4); // stat card + 3 status badges
      expect(screen.getByText('3')).toBeInTheDocument(); // submitted count
      expect(screen.getAllByText('Pending Sign-offs')).toHaveLength(2); // stat card + queue
      expect(screen.getByText('6')).toBeInTheDocument(); // sign-offs count (the stat shows 6)
      expect(screen.getByText('Changes Requested')).toBeInTheDocument();
      expect(screen.getByText('Approved')).toBeInTheDocument();
    });
  });

  it('displays submitted content with sign-off counts', async () => {
    render(<ManagerLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText('Submitted Article 1')).toBeInTheDocument();
      expect(screen.getByText('Submitted Article 2')).toBeInTheDocument();
      expect(screen.getByText('Submitted Article 3')).toBeInTheDocument();
    });

    // Check sign-off indicators - text might be split across elements
    // Use getAllByText since there are multiple matches
    expect(screen.getAllByText((content: string) => /sign.*off.*pending/i.test(content)).length).toBeGreaterThan(0);
    // "Submitted" appears in stat card and 3 status badges - use getAllByText
    expect(screen.getAllByText('Submitted').length).toBeGreaterThan(0);
  });

  it('shows coming soon for disabled actions', async () => {
    render(<ManagerLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getAllByText('Review Queue')).toHaveLength(1);
      expect(screen.getByText('Content awaiting decision')).toBeInTheDocument();
      expect(screen.getAllByText('Pending Sign-offs')).toHaveLength(2); // stat card + quick action
      expect(screen.getAllByText('Coming soon')).toHaveLength(2); // Pending Sign-offs and Approval History
      expect(screen.getByText('Approval History')).toBeInTheDocument();
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
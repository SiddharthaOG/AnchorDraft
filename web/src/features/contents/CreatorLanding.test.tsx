/** Tests for CreatorLanding component. */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { CreatorLanding } from './CreatorLanding';

// Mock the data layer using vi.hoisted
const { mockGetContents, mockGetContentStats } = vi.hoisted(() => ({
  mockGetContents: vi.fn(),
  mockGetContentStats: vi.fn(),
}));

vi.mock('../../lib/data', () => ({
  getContents: mockGetContents,
  getContentStats: mockGetContentStats,
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

describe('CreatorLanding', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetContentStats.mockResolvedValue({
      total: 4,
      draft: 2,
      submitted: 1,
      changes_requested: 1,
      approved: 0,
    });
    mockGetContents.mockResolvedValue([
      { id: 'content-1', title: 'Blog Post 1', channel: 'blog', status: 'draft', purpose: 'Educational', created_at: '2026-01-01T00:00:00Z' },
      { id: 'content-2', title: 'LinkedIn Post', channel: 'linkedin', status: 'submitted', purpose: 'Announcement', created_at: '2026-01-02T00:00:00Z' },
      { id: 'content-3', title: 'Email Draft', channel: 'email', status: 'changes_requested', purpose: 'Newsletter', created_at: '2026-01-03T00:00:00Z' },
      { id: 'content-4', title: 'Approved Article', channel: 'website', status: 'approved', purpose: 'Documentation', created_at: '2026-01-04T00:00:00Z' },
    ]);
  });

  afterEach(() => {
    cleanup();
  });

  it('shows loading screen while data is loading', async () => {
    let resolveStats: (value: any) => void;
    let resolveContents: (value: any) => void;
    const statsPromise = new Promise(resolve => { resolveStats = resolve; });
    const contentsPromise = new Promise(resolve => { resolveContents = resolve; });
    mockGetContentStats.mockReturnValueOnce(statsPromise);
    mockGetContents.mockReturnValueOnce(contentsPromise);

    render(<CreatorLanding />, { wrapper: TestWrapper });

    // LoadingScreen shows "Loading content data..." for CreatorLanding
    expect(screen.getByText('Loading content data...')).toBeInTheDocument();

    resolveStats!({ total: 0, draft: 0, submitted: 0, changes_requested: 0, approved: 0 });
    resolveContents!([]);

    await waitFor(() => {
      expect(screen.queryByText('Loading content data...')).not.toBeInTheDocument();
    });
  });

  it('shows error state when data fetch fails', async () => {
    mockGetContentStats.mockRejectedValueOnce(new Error('Network error'));

    render(<CreatorLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText('Unable to load data')).toBeInTheDocument();
    });
    expect(screen.getByText('Network error')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('shows empty state when no content', async () => {
    mockGetContents.mockResolvedValueOnce([]);
    mockGetContentStats.mockResolvedValueOnce({ total: 0, draft: 0, submitted: 0, changes_requested: 0, approved: 0 });

    render(<CreatorLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText('No content yet')).toBeInTheDocument();
    });
    expect(screen.getByText('Create your first draft')).toBeInTheDocument();
  });

  it('displays content stats', async () => {
    render(<CreatorLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText('Drafts')).toBeInTheDocument();
      expect(screen.getByText('Submitted')).toBeInTheDocument();
      expect(screen.getByText('In Review')).toBeInTheDocument();
      expect(screen.getByText('Approved')).toBeInTheDocument();
      expect(screen.getByText('2')).toBeInTheDocument(); // draft
      expect(screen.getAllByText('1')).toHaveLength(2); // submitted and changes_requested both 1
      expect(screen.getByText('0')).toBeInTheDocument(); // approved
    });
  });

  it('displays recent content list with status badges', async () => {
    render(<CreatorLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText('Blog Post 1')).toBeInTheDocument();
      expect(screen.getByText('LinkedIn Post')).toBeInTheDocument();
      expect(screen.getByText('Email Draft')).toBeInTheDocument();
      expect(screen.getByText('Approved Article')).toBeInTheDocument();
    });

    // Check status badges
    expect(screen.getByText('draft')).toBeInTheDocument();
    expect(screen.getByText('submitted')).toBeInTheDocument();
    expect(screen.getByText('changes requested')).toBeInTheDocument();
    expect(screen.getByText('approved')).toBeInTheDocument();
    expect(screen.getByText('blog')).toBeInTheDocument();
    expect(screen.getByText('linkedin')).toBeInTheDocument();
    expect(screen.getByText('email')).toBeInTheDocument();
    expect(screen.getByText('website')).toBeInTheDocument();
  });

  it('shows coming soon for disabled actions', async () => {
    render(<CreatorLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText('Create New Content')).toBeInTheDocument();
      expect(screen.getByText('My Content')).toBeInTheDocument();
      expect(screen.getByText('Import Document')).toBeInTheDocument();
      expect(screen.getAllByText('Coming soon')).toHaveLength(3);
    });
  });

  it('limits recent content to 5 items', async () => {
    mockGetContents.mockResolvedValueOnce([
      { id: '1', title: 'A', channel: 'blog', status: 'draft', purpose: 'p' },
      { id: '2', title: 'B', channel: 'blog', status: 'draft', purpose: 'p' },
      { id: '3', title: 'C', channel: 'blog', status: 'draft', purpose: 'p' },
      { id: '4', title: 'D', channel: 'blog', status: 'draft', purpose: 'p' },
      { id: '5', title: 'E', channel: 'blog', status: 'draft', purpose: 'p' },
      { id: '6', title: 'F', channel: 'blog', status: 'draft', purpose: 'p' },
    ]);

    render(<CreatorLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText('Showing 5 of 6 content items')).toBeInTheDocument();
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
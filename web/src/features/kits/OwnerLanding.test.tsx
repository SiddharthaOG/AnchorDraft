/** Tests for OwnerLanding component. */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { OwnerLanding } from './OwnerLanding';

// Mock the data layer using vi.hoisted
const { mockGetKitStats, mockGetKitRules, mockGetKitFacts } = vi.hoisted(() => ({
  mockGetKitStats: vi.fn(),
  mockGetKitRules: vi.fn(),
  mockGetKitFacts: vi.fn(),
}));

vi.mock('../../lib/data', () => ({
  getKitStats: mockGetKitStats,
  getKitRules: mockGetKitRules,
  getKitFacts: mockGetKitFacts,
}));

// Mock the auth service using vi.hoisted
const { mockSession: mockOwnerSession } = vi.hoisted(() => ({
  mockSession: {
    user: { id: 'user-1', email: 'owner@example.com' },
    profile: { display_name: 'Test Owner', user_id: 'user-1', created_at: '2026-01-01' },
    memberships: [{ org_id: 'org-1', user_id: 'user-1', roles: ['owner'], created_at: '2026-01-01' }],
    organizations: [{ id: 'org-1', name: 'Test Org', created_at: '2026-01-01' }],
    currentOrgId: 'org-1',
    currentOrgName: 'Test Org',
    currentRoles: ['owner'],
    isLoading: false,
    error: null,
  },
}));

vi.mock('../../features/auth/AuthProvider', () => ({
  useAuth: () => ({
    session: mockOwnerSession,
    isLoading: false,
    error: null,
    signInWithEmail: vi.fn(),
    signInWithOAuth: vi.fn(),
    signOut: vi.fn(),
    switchOrganization: vi.fn(),
    hasRole: vi.fn((role: string) => mockOwnerSession.currentRoles.includes(role)),
    hasAnyRole: vi.fn((roles: string[]) => roles.some(role => mockOwnerSession.currentRoles.includes(role))),
    getPrimaryRole: vi.fn(() => 'owner'),
    refreshSession: vi.fn(),
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));

function TestWrapper({ children }: { children: React.ReactNode }) {
  return (
    <MemoryRouter>
      {children}
    </MemoryRouter>
  );
}

describe('OwnerLanding', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetKitStats.mockResolvedValue({
      total_kits: 2,
      active_kit: {
        id: 'kit-1',
        org_id: 'org-1',
        version: 1,
        name: 'Test Kit v1',
        status: 'active',
        source_kit_id: null,
        created_by: 'user-1',
        created_at: '2026-01-01T00:00:00Z',
        activated_at: '2026-01-01T00:00:00Z',
      },
      draft_kits: 1,
      total_rules: 5,
      total_facts: 3,
    });
    mockGetKitRules.mockResolvedValue([
      { id: 'rule-1', rule_key: 'TERM-01', category: 'terminology', check_kind: 'deterministic', severity: 'low', guideline_text: 'Use simple language', title: 'Simple terms', config: {}, needs_reviewer: false, example_bad: 'utilize', example_good: 'use' },
      { id: 'rule-2', rule_key: 'CLAIM-01', category: 'claim', check_kind: 'llm', severity: 'high', guideline_text: 'No absolute claims', title: 'No absolutes', config: null, needs_reviewer: true, example_bad: 'guaranteed', example_good: '99.9% uptime' },
      { id: 'rule-3', rule_key: 'A11Y-01', category: 'accessibility', check_kind: 'deterministic', severity: 'high', guideline_text: 'Alt text required', title: 'Alt text', config: {}, needs_reviewer: false, example_bad: '![image](x.png)', example_good: '![Chart](x.png)' },
    ]);
    mockGetKitFacts.mockResolvedValue([
      { id: 'fact-1', fact_key: 'FACT-01', statement: '99.9% uptime', source_note: 'SLA doc', valid_until: '2027-01-01' },
      { id: 'fact-2', fact_key: 'FACT-02', statement: 'SOC 2 certified', source_note: 'Audit report', valid_until: '2027-06-01' },
    ]);
  });

  afterEach(() => {
    cleanup();
  });

  it('shows loading screen while data is loading', async () => {
    let resolveData: (value: any) => void;
    const dataPromise = new Promise(resolve => { resolveData = resolve; });
    mockGetKitStats.mockReturnValueOnce(dataPromise);

    render(<OwnerLanding />, { wrapper: TestWrapper });

    // LoadingScreen shows "Loading brand kit data..." initially
    expect(screen.getByText('Loading brand kit data...')).toBeInTheDocument();

    resolveData!({
      total_kits: 1,
      active_kit: null,
      draft_kits: 0,
      total_rules: 0,
      total_facts: 0,
    });

    await waitFor(() => {
      expect(screen.queryByText('Loading brand kit data...')).not.toBeInTheDocument();
    });
  });

  it('shows error state when data fetch fails', async () => {
    mockGetKitStats.mockRejectedValueOnce(new Error('Network error'));

    render(<OwnerLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText('Unable to load data')).toBeInTheDocument();
    });
    expect(screen.getByText('Network error')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('shows empty state when no active kit', async () => {
    mockGetKitStats.mockResolvedValueOnce({
      total_kits: 0,
      active_kit: null,
      draft_kits: 0,
      total_rules: 0,
      total_facts: 0,
    });

    render(<OwnerLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText('No active brand kit')).toBeInTheDocument();
    });
    expect(screen.getByText('Create your first brand kit')).toBeInTheDocument();
  });

  it('displays active kit stats', async () => {
    render(<OwnerLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText('Test Kit v1')).toBeInTheDocument();
      // Version text may be split across elements
      expect(screen.getByText(/Version 1/i)).toBeInTheDocument();
    });

    // Use getAllByText for duplicate texts
    expect(screen.getAllByText('Active Kit')).toHaveLength(1);
    expect(screen.getAllByText('Draft Kits')).toHaveLength(1);
    expect(screen.getAllByText('Rules')).toHaveLength(1);
    expect(screen.getAllByText('Approved Facts')).toHaveLength(2); // stat card + section header
    expect(screen.getByText('5')).toBeInTheDocument(); // total_rules
    expect(screen.getByText('3')).toBeInTheDocument(); // total_facts
  });

  it('displays rules grouped by category', async () => {
    render(<OwnerLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      // Category names are uppercase in the component
      expect(screen.getByText(/terminology/i)).toBeInTheDocument();
      expect(screen.getByText(/claim/i)).toBeInTheDocument();
      expect(screen.getByText(/accessibility/i)).toBeInTheDocument();
      // There are two categories with "1 deterministic, 0 LLM" - use getAllByText
      const deterministicItems = screen.getAllByText('1 deterministic, 0 LLM');
      expect(deterministicItems.length).toBeGreaterThanOrEqual(2);
      const llmItems = screen.getAllByText('0 deterministic, 1 LLM');
      expect(llmItems.length).toBeGreaterThanOrEqual(1);
    });
  });

  it('displays approved facts', async () => {
    render(<OwnerLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText('FACT-01')).toBeInTheDocument();
      expect(screen.getByText('99.9% uptime')).toBeInTheDocument();
      expect(screen.getByText('FACT-02')).toBeInTheDocument();
      expect(screen.getByText('SOC 2 certified')).toBeInTheDocument();
    });
  });

  it('shows coming soon for disabled actions', async () => {
    render(<OwnerLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText('Create Brand Kit')).toBeInTheDocument();
      expect(screen.getAllByText('Coming soon')).toHaveLength(2); // Create Brand Kit and Lint Kit
      expect(screen.getByText('Lint Kit')).toBeInTheDocument();
    });
  });

  it('shows Manage Kits link as active', async () => {
    render(<OwnerLanding />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText('Manage Kits')).toBeInTheDocument();
      expect(screen.getByText('View and edit kits')).toBeInTheDocument();
    });
  });
});
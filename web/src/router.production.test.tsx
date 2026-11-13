import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { RouterProvider } from 'react-router-dom'
import { AuthProvider } from './features/auth/AuthProvider'
import { createMemoryAppRouter } from './router'

const { serviceState, mockInitializeSession, mockSignInWithEmail, mockGetContents, mockGetContentStats } = vi.hoisted(() => ({
  serviceState: {
    currentSession: null as any,
    listeners: new Set<(session: any) => void>(),
  },
  mockInitializeSession: vi.fn(),
  mockSignInWithEmail: vi.fn(),
  mockGetContents: vi.fn(),
  mockGetContentStats: vi.fn(),
}))

vi.mock('./features/auth/authService', () => ({
  initializeSession: mockInitializeSession,
  onAuthStateChange: vi.fn(() => ({ unsubscribe: vi.fn() })),
  subscribeToSession: (listener: (session: any) => void) => {
    serviceState.listeners.add(listener)
    listener(serviceState.currentSession)
    return () => serviceState.listeners.delete(listener)
  },
  signInWithEmail: mockSignInWithEmail,
  signInWithOAuth: vi.fn().mockResolvedValue({ error: null }),
  signOut: vi.fn().mockResolvedValue({ error: null }),
  switchOrganization: vi.fn().mockResolvedValue({ error: null }),
}))

vi.mock('./lib/data', () => ({
  getContents: mockGetContents,
  getContentStats: mockGetContentStats,
}))

// Keep this route integration test focused on auth + protected routing.
// Feature-specific rendering/data behavior is covered by each feature's tests.
vi.mock('./features/contents/CreatorLanding', () => ({
  CreatorLanding: () => <div>Welcome back, Test</div>,
}))

vi.mock('./features/contents/ContentDetail', () => ({
  ContentDetail: () => <div>Submitted content detail</div>,
}))

const creatorSession = {
  user: { id: 'creator-1', email: 'creator@example.com' },
  profile: { display_name: 'Test Creator' },
  currentRoles: ['creator'],
  organizations: [{ id: 'org-1', name: 'Test Org' }],
  currentOrgId: 'org-1',
  currentOrgName: 'Test Org',
  memberships: [{ org_id: 'org-1', user_id: 'creator-1', roles: ['creator'] }],
  isLoading: false,
  error: null,
}

function publishSession(session: typeof creatorSession | null) {
  serviceState.currentSession = session
  for (const listener of serviceState.listeners) listener(session)
}

describe('production login-to-dashboard route', () => {
  beforeEach(() => {
    serviceState.currentSession = null
    serviceState.listeners.clear()
    vi.clearAllMocks()

    mockInitializeSession.mockResolvedValue(null)
    mockSignInWithEmail.mockImplementation(async () => {
      publishSession(creatorSession)
      return { error: null }
    })
    mockGetContents.mockResolvedValue([])
    mockGetContentStats.mockResolvedValue({
      total: 0,
      draft: 0,
      submitted: 0,
      changes_requested: 0,
      approved: 0,
    })
  })

  afterEach(() => {
    cleanup()
  })

  it('renders both OAuth provider symbols on the real login route', async () => {
    const router = createMemoryAppRouter(['/login'])
    render(
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>,
    )

    const googleButton = await screen.findByRole('button', { name: 'Google' })
    const githubButton = screen.getByRole('button', { name: 'GitHub' })

    expect(googleButton.querySelector('svg')).toBeInTheDocument()
    expect(githubButton.querySelector('svg')).toBeInTheDocument()
    expect(googleButton.querySelectorAll('svg path')).toHaveLength(4)
    expect(githubButton.querySelectorAll('svg path')).toHaveLength(1)
  })

  it('moves from successful email login into the real protected creator dashboard', async () => {
    const router = createMemoryAppRouter(['/login'])
    const { container } = render(
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>,
    )

    await screen.findByText('Sign in to AnchorDraft')
    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'creator@example.com' },
    })
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'test-password' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in with email' }))

    expect(await screen.findByText('Welcome back, Test')).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Main navigation' })).toBeInTheDocument()
    expect(screen.getByText('Welcome back, Test')).toBeInTheDocument()
    expect(container.querySelector('.anchordraft-shell')).toBeInTheDocument()
    expect(container.querySelector('.anchordraft-sidebar')).toBeInTheDocument()
    expect(container.querySelector('.anchordraft-main')).toBeInTheDocument()
    expect(container.querySelector('[class^="ad-"], [class*=" ad-"]')).not.toBeInTheDocument()
    expect(container.querySelector('.anchordraft-page .anchordraft-route-transition')).not.toBeEmptyDOMElement()
    expect(mockSignInWithEmail).toHaveBeenCalledWith('creator@example.com', 'test-password')
  })

  it('allows an authenticated owner to open a submitted item from approvals', async () => {
    mockInitializeSession.mockResolvedValue({
      ...creatorSession,
      currentRoles: ['owner'],
    })

    const router = createMemoryAppRouter(['/approvals/content-123'])
    render(
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>,
    )

    expect(await screen.findByText('Submitted content detail')).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Main navigation' })).toBeInTheDocument()
  })

  it('requires authentication before opening an approvals item directly', async () => {
    mockInitializeSession.mockResolvedValue(null)

    const router = createMemoryAppRouter(['/approvals/content-123'])
    render(
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>,
    )

    expect(await screen.findByText('Sign in to AnchorDraft')).toBeInTheDocument()
  })
})

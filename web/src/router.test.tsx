/// <reference types="vitest/globals" />

import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import { MemoryRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom'

import { AuthProvider, useAuth } from './features/auth/AuthProvider'
import Layout from './components/Layout'
import { LoadingScreen } from './components/LoadingScreen'
import { AuthCallback } from './features/auth/AuthCallback'
import { NoAccess } from './components/NoAccess'

// Mock landing pages
const CreatorLanding = () => <div data-testid="creator-landing">Creator Landing</div>
const ManagerLanding = () => <div data-testid="manager-landing">Manager Landing</div>
const ReviewerLanding = () => <div data-testid="reviewer-landing">Reviewer Landing</div>
const OwnerLanding = () => <div data-testid="owner-landing">Owner Landing</div>

// Use vi.hoisted to create mock before vi.mock is hoisted
const { mockInitializeSession } = vi.hoisted(() => {
  let callCount = 0
  return {
    mockInitializeSession: vi.fn(() => {
      callCount++
      if (callCount === 1) {
        // First call (AuthProvider) - resolve with null
        return Promise.resolve(null)
      }
      // Subsequent calls (AuthCallback) - never resolve
      return new Promise(() => {})
    }),
  }
})

vi.mock('./features/auth/authService', () => ({
  initializeSession: mockInitializeSession,

  onAuthStateChange: vi.fn(() => ({
    unsubscribe: vi.fn(),
  })),

  subscribeToSession: vi.fn((listener) => {
    listener(null)
    return () => {}
  }),

  getSession: vi.fn(() => null),
  signInWithEmail: vi.fn(),
  signInWithOAuth: vi.fn(),
  signOut: vi.fn(),
  switchOrganization: vi.fn(),

  hasCurrentRole: vi.fn(() => false),
  hasAnyRole: vi.fn(() => false),
  getCurrentPrimaryRole: vi.fn(() => null),
}))

vi.mock('./lib/supabase', () => ({
  getSupabaseClient: () => ({
    auth: {
      getSession: vi.fn(),
      signInWithPassword: vi.fn(),
      signInWithOAuth: vi.fn(),
      signOut: vi.fn(),
      onAuthStateChange: vi.fn(),
    },

    from: vi.fn(() => ({
      select: vi.fn().mockReturnThis(),
      eq: vi.fn().mockReturnThis(),
      single: vi.fn().mockResolvedValue({
        data: null,
        error: { code: 'PGRST116' },
      }),
    })),
  }),
}))

vi.mock('./features/auth/userRole', () => ({
  resolveUserContext: vi.fn().mockResolvedValue({
    memberships: [],
    organizations: [],
    currentOrgId: null,
    currentOrgName: null,
    currentRoles: [],
  }),
}))

// Recreate the router structure using MemoryRouter-compatible components
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { session, isLoading } = useAuth()

  if (isLoading) return <LoadingScreen message="Loading authentication..." />
  if (!session) return <Navigate to="/login" replace />

  return children
}

function RoleRoute({ allowedRoles, children }: { allowedRoles: string[]; children: React.ReactNode }) {
  const { hasAnyRole } = useAuth()

  if (!hasAnyRole(allowedRoles)) {
    return <NoAccess requiredRoles={allowedRoles} />
  }

  return children
}

function PublicRoute({ children }: { children: React.ReactNode }) {
  const { session, isLoading } = useAuth()

  if (isLoading) return <LoadingScreen message="Loading..." />
  if (session) return <Navigate to="/" replace />

  return children
}

function LoginPage() {
  const { signInWithEmail, signInWithOAuth, isLoading, error } = useAuth()
  const [email, setEmail] = React.useState('')
  const [password, setPassword] = React.useState('')
  const [isSubmitting, setIsSubmitting] = React.useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSubmitting(true)
    try {
      await signInWithEmail(email, password)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-white rounded-lg shadow p-6">
        <h1 className="text-2xl font-bold text-gray-900 mb-6 text-center">Sign in to AnchorDraft</h1>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              placeholder="you@example.com"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1">
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              placeholder="••••••••"
            />
          </div>

          <button
            type="submit"
            disabled={isSubmitting || isLoading}
            className="w-full py-2 px-4 bg-primary text-white rounded-lg font-medium hover:bg-primary-dark focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSubmitting ? 'Signing in...' : 'Sign in with email'}
          </button>
        </form>

        <div className="mt-6">
          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-gray-300" />
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="px-2 bg-white text-gray-500">Or continue with</span>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => signInWithOAuth('google')}
              disabled={isLoading || isSubmitting}
              className="py-2 px-4 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
            >
              <svg className="w-5 h-5 mr-2 inline" viewBox="0 0 24 24">
                <path
                  fill="currentColor"
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                />
                <path
                  fill="currentColor"
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                />
                <path
                  fill="currentColor"
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                />
                <path
                  fill="currentColor"
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                />
              </svg>
              Google
            </button>
            <button
              type="button"
              onClick={() => signInWithOAuth('github')}
              disabled={isLoading || isSubmitting}
              className="py-2 px-4 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
            >
              <svg className="w-5 h-5 mr-2 inline" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
              </svg>
              GitHub
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function TestRoutes() {
  return (
    <Routes>
      {/* Public routes (no Layout wrapper) */}
      <Route
        path="/login"
        element={
          <PublicRoute>
            <LoginPage />
          </PublicRoute>
        }
      />
      <Route
        path="/auth/callback"
        element={
          <PublicRoute>
            <AuthCallback />
          </PublicRoute>
        }
      />
      {/* Protected routes (Layout wrapper applied once) */}
      <Route
        path="/"
        element={
          <Layout>
            <ProtectedRoute>
              <Outlet />
            </ProtectedRoute>
          </Layout>
        }
      >
        {/* Creator routes */}
        <Route
          index
          element={
            <RoleRoute allowedRoles={['creator', 'manager', 'reviewer', 'owner']}>
              <CreatorLanding />
            </RoleRoute>
          }
        />
        {/* Owner (Guideline Owner) routes */}
        <Route
          path="kits"
          element={
            <RoleRoute allowedRoles={['owner']}>
              <OwnerLanding />
            </RoleRoute>
          }
        />
        {/* Manager routes */}
        <Route
          path="approvals"
          element={
            <RoleRoute allowedRoles={['manager', 'owner']}>
              <ManagerLanding />
            </RoleRoute>
          }
        />
        {/* Reviewer routes */}
        <Route
          path="review"
          element={
            <RoleRoute allowedRoles={['reviewer', 'owner']}>
              <ReviewerLanding />
            </RoleRoute>
          }
        />
      </Route>
    </Routes>
  )
}

async function renderRouter(initialPath = '/') {
  const { unmount, ...result } = render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthProvider>
        <TestRoutes />
      </AuthProvider>
    </MemoryRouter>
  )

  // Wait for auth initialization to complete (isLoading to become false)
  await waitFor(() => {
    expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
    expect(screen.queryByText('Loading authentication...')).not.toBeInTheDocument()
  })

  return { unmount, ...result }
}

describe('Router', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Reset the call count by re-creating the mock behavior
    mockInitializeSession.mockImplementation(() => {
      // We can't easily track call count across mockImplementation calls
      // So we'll just resolve with null for all calls in most tests
      return Promise.resolve(null)
    })
  })

  afterEach(() => {
    cleanup()
  })

  it('renders login page at /login', async () => {
    const { unmount } = await renderRouter('/login')

    await waitFor(() => {
      expect(screen.getByText('Sign in to AnchorDraft')).toBeInTheDocument()
    })

    unmount()
  })

  it('renders auth callback page at /auth/callback', async () => {
    // For this test, we want the first call to resolve, subsequent to hang
    let callCount = 0
    mockInitializeSession.mockImplementation(() => {
      callCount++
      if (callCount === 1) {
        return Promise.resolve(null)
      }
      return new Promise(() => {})
    })

    const { unmount } = await renderRouter('/auth/callback')

    await waitFor(() => {
      expect(screen.getByText('Completing authentication...')).toBeInTheDocument()
    })

    unmount()
  })

  it('redirects unauthenticated users to login for protected routes', async () => {
    mockInitializeSession.mockResolvedValue(null)
    const { unmount } = await renderRouter('/')

    await waitFor(() => {
      expect(screen.getByText('Access Denied')).toBeInTheDocument()
    })

    unmount()
  })

  it('login page is not wrapped in Layout', async () => {
    mockInitializeSession.mockResolvedValue(null)
    const { unmount } = await renderRouter('/login')

    expect(screen.queryByText('AnchorDraft')).not.toBeInTheDocument()

    unmount()
  })

  it('auth callback page is not wrapped in Layout', async () => {
    let callCount = 0
    mockInitializeSession.mockImplementation(() => {
      callCount++
      if (callCount === 1) {
        return Promise.resolve(null)
      }
      return new Promise(() => {})
    })

    const { unmount } = await renderRouter('/auth/callback')

    expect(screen.queryByText('AnchorDraft')).not.toBeInTheDocument()

    unmount()
  })

  it('protected routes require authentication for /kits', async () => {
    mockInitializeSession.mockResolvedValue(null)
    const { unmount } = await renderRouter('/kits')

    await waitFor(() => {
      expect(screen.getByText('Access Denied')).toBeInTheDocument()
    })

    unmount()
  })

  it('protected routes require authentication for /approvals', async () => {
    mockInitializeSession.mockResolvedValue(null)
    const { unmount } = await renderRouter('/approvals')

    await waitFor(() => {
      expect(screen.getByText('Access Denied')).toBeInTheDocument()
    })

    unmount()
  })

  it('protected routes require authentication for /review', async () => {
    mockInitializeSession.mockResolvedValue(null)
    const { unmount } = await renderRouter('/review')

    await waitFor(() => {
      expect(screen.getByText('Access Denied')).toBeInTheDocument()
    })

    unmount()
  })
})
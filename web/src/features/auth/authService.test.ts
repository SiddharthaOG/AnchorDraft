/// <reference types="vitest/globals" />

import {
  describe,
  it,
  expect,
  vi,
  beforeEach,
  afterEach,
} from 'vitest'

import {
  initializeSession,
  signOut,
  onAuthStateChange,
  subscribeToSession,
  getSession,
  signInWithEmail,
  signInWithOAuth,
  switchOrganization,
  hasCurrentRole,
  hasAnyCurrentRole,
  getCurrentPrimaryRole,
} from './authService'

const {
  mockSupabaseAuth,
  mockResolveUserContext,
} = vi.hoisted(() => ({
  mockSupabaseAuth: {
    getSession: vi.fn(),
    signInWithPassword: vi.fn(),
    signInWithOAuth: vi.fn(),
    signOut: vi.fn(),
    onAuthStateChange: vi.fn(),
  },
  mockResolveUserContext: vi.fn(),
}))

vi.mock('../../lib/supabase', () => ({
  getSupabaseClient: () => ({
    auth: mockSupabaseAuth,
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

vi.mock('./userRole', () => ({
  resolveUserContext: mockResolveUserContext,
}))

const testUser = {
  id: 'user-1',
  email: 'test@example.com',
  user_metadata: {},
  app_metadata: {},
  aud: 'authenticated',
  created_at: '2024-01-01T00:00:00Z',
}

function makeSupabaseSession() {
  return {
    user: testUser,
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void

  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })

  return { promise, resolve, reject }
}

function defaultUserContext() {
  return {
    memberships: [],
    organizations: [],
    currentOrgId: null,
    currentOrgName: null,
    currentRoles: ['creator'],
  }
}

describe('authService', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()

    mockResolveUserContext.mockResolvedValue(defaultUserContext())

    mockSupabaseAuth.onAuthStateChange.mockImplementation(
      () => ({
        data: {
          subscription: {
            unsubscribe: vi.fn(),
          },
        },
      }),
    )

    mockSupabaseAuth.signOut.mockResolvedValue({
      error: null,
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('initializeSession', () => {
    it('returns null when no session exists', async () => {
      mockSupabaseAuth.getSession.mockResolvedValue({
        data: { session: null },
        error: null,
      })

      const result = await initializeSession()

      expect(result).toBeNull()
    })

    it('throws on Supabase auth error', async () => {
      mockSupabaseAuth.getSession.mockResolvedValue({
        data: { session: null },
        error: { message: 'Auth error' },
      })

      await expect(initializeSession()).rejects.toThrow(
        'Authentication initialization failed: Auth error',
      )
    })

    it('builds session from user when session exists', async () => {
      mockSupabaseAuth.getSession.mockResolvedValue({
        data: {
          session: makeSupabaseSession(),
        },
        error: null,
      })

      const result = await initializeSession()

      expect(result).not.toBeNull()
      expect(result?.user.id).toBe('user-1')
      expect(result?.currentRoles).toContain('creator')
    })
  })

  describe('signOut', () => {
    it('clears session on successful sign out', async () => {
      mockSupabaseAuth.getSession.mockResolvedValue({
        data: {
          session: makeSupabaseSession(),
        },
        error: null,
      })

      await initializeSession()

      expect(getSession()).not.toBeNull()

      const result = await signOut()

      expect(result.error).toBeNull()
      expect(getSession()).toBeNull()
    })

    it('returns error on sign out failure', async () => {
      mockSupabaseAuth.signOut.mockResolvedValue({
        error: { message: 'Sign out failed' },
      })

      const result = await signOut()

      expect(result.error).toBe('Sign out failed')
    })
  })

  describe('stale session invalidation', () => {
    it('does not restore an initialization after sign out', async () => {
      const pendingContext = deferred<ReturnType<typeof defaultUserContext>>()

      mockResolveUserContext.mockReturnValue(pendingContext.promise)

      mockSupabaseAuth.getSession.mockResolvedValue({
        data: {
          session: makeSupabaseSession(),
        },
        error: null,
      })

      const initPromise = initializeSession()

      // Allow getSession() to resolve and the context build to begin.
      await Promise.resolve()

      expect(mockResolveUserContext).toHaveBeenCalled()

      await signOut()

      expect(getSession()).toBeNull()

      // Finish the old asynchronous build after sign out.
      pendingContext.resolve(defaultUserContext())

      const result = await initPromise

      expect(result).toBeNull()
      expect(getSession()).toBeNull()
    })

    it('does not apply a pending SIGNED_IN build after SIGNED_OUT', async () => {
      const pendingContext = deferred<ReturnType<typeof defaultUserContext>>()

      mockResolveUserContext.mockReturnValue(pendingContext.promise)

      let authCallback:
        | ((event: string, session: any) => void)
        | undefined

      mockSupabaseAuth.onAuthStateChange.mockImplementation(
        (callback: (event: string, session: any) => void) => {
          authCallback = callback

          return {
            data: {
              subscription: {
                unsubscribe: vi.fn(),
              },
            },
          }
        },
      )

      const subscription = onAuthStateChange(() => {})

      authCallback?.('SIGNED_IN', makeSupabaseSession())

      // Run the queued auth-event handler until the async build starts.
      await Promise.resolve()
      await Promise.resolve()

      expect(mockResolveUserContext).toHaveBeenCalled()

      // A newer SIGNED_OUT event invalidates the pending SIGNED_IN build.
      authCallback?.('SIGNED_OUT', null)

      await Promise.resolve()

      pendingContext.resolve(defaultUserContext())

      await Promise.resolve()
      await Promise.resolve()

      expect(getSession()).toBeNull()

      subscription.unsubscribe()
    })
  })

  describe('session subscriptions', () => {
    it('immediately provides the current session to subscribers', () => {
      const sessions: any[] = []

      const unsubscribe = subscribeToSession((session) => {
        sessions.push(session)
      })

      expect(sessions).toHaveLength(1)
      expect(sessions[0]).toBe(getSession())

      unsubscribe()
    })
  })

  describe('signInWithEmail', () => {
    it('returns error on invalid credentials', async () => {
      mockSupabaseAuth.signInWithPassword.mockResolvedValue({
        error: { message: 'Invalid credentials' },
      })

      const result = await signInWithEmail(
        'test@example.com',
        'wrong',
      )

      expect(result.error).toBe('Invalid credentials')
    })

    it('initializes session on successful sign in', async () => {
      mockSupabaseAuth.signInWithPassword.mockResolvedValue({
        error: null,
      })

      mockSupabaseAuth.getSession.mockResolvedValue({
        data: {
          session: makeSupabaseSession(),
        },
        error: null,
      })

      const result = await signInWithEmail(
        'test@example.com',
        'password',
      )

      expect(result.error).toBeNull()
      expect(getSession()?.user.id).toBe('user-1')
    })
  })

  describe('signInWithOAuth', () => {
    it('initiates OAuth flow with the callback redirect', async () => {
      mockSupabaseAuth.signInWithOAuth.mockResolvedValue({
        error: null,
      })

      const result = await signInWithOAuth('google')

      expect(result.error).toBeNull()

      expect(mockSupabaseAuth.signInWithOAuth).toHaveBeenCalledWith({
        provider: 'google',
        options: {
          redirectTo: `${window.location.origin}/auth/callback`,
        },
      })
    })

    it('returns OAuth provider errors', async () => {
      mockSupabaseAuth.signInWithOAuth.mockResolvedValue({
        error: { message: 'OAuth unavailable' },
      })

      const result = await signInWithOAuth('google')

      expect(result.error).toBe('OAuth unavailable')
    })
  })

  describe('switchOrganization', () => {
    it('returns error when no session exists', async () => {
      // Explicitly establish the no-session state.
      mockSupabaseAuth.getSession.mockResolvedValue({
        data: { session: null },
        error: null,
      })

      await initializeSession()

      expect(getSession()).toBeNull()

      const result = await switchOrganization('org-1')

      expect(result.error).toBe('No active session')
    })

    it('returns error when not a member', async () => {
      mockSupabaseAuth.getSession.mockResolvedValue({
        data: {
          session: makeSupabaseSession(),
        },
        error: null,
      })

      await initializeSession()

      const result = await switchOrganization('org-unknown')

      expect(result.error).toBe(
        'Not a member of this organization',
      )
    })
  })

  describe('role checking', () => {
    beforeEach(async () => {
      mockSupabaseAuth.getSession.mockResolvedValue({
        data: {
          session: makeSupabaseSession(),
        },
        error: null,
      })

      await initializeSession()
    })

    it('hasCurrentRole returns true for matching role', () => {
      expect(hasCurrentRole('creator')).toBe(true)
    })

    it('hasCurrentRole returns false for non-matching role', () => {
      expect(hasCurrentRole('owner')).toBe(false)
    })

    it('hasAnyCurrentRole returns true when any role matches', () => {
      expect(hasAnyCurrentRole(['owner', 'creator'])).toBe(true)
    })

    it('hasAnyCurrentRole returns false when no roles match', () => {
      expect(hasAnyCurrentRole(['owner', 'manager'])).toBe(false)
    })

    it('getCurrentPrimaryRole returns highest priority role', () => {
      expect(getCurrentPrimaryRole()).toBe('creator')
    })
  })
})
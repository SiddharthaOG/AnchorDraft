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
  render,
  screen,
  waitFor,
  act,
  cleanup,
} from '@testing-library/react'

import { AuthProvider, useAuth } from './AuthProvider'

import {
  initializeSession,
  onAuthStateChange,
  subscribeToSession,
  signInWithEmail,
  signInWithOAuth,
  signOut,
  switchOrganization,
} from './authService'

vi.mock('./authService', () => ({
  initializeSession: vi.fn(),
  onAuthStateChange: vi.fn(),
  subscribeToSession: vi.fn(),
  getSession: vi.fn(),
  signInWithEmail: vi.fn(),
  signInWithOAuth: vi.fn(),
  signOut: vi.fn(),
  switchOrganization: vi.fn(),
  hasCurrentRole: vi.fn(),
  hasAnyRole: vi.fn(),
  getCurrentPrimaryRole: vi.fn(),
}))

const mockedInitializeSession = vi.mocked(initializeSession)
const mockedOnAuthStateChange = vi.mocked(onAuthStateChange)
const mockedSubscribeToSession = vi.mocked(subscribeToSession)

const TestComponent = () => {
  const {
    session,
    isLoading,
    error,
    signInWithEmail: signIn,
    signInWithOAuth: signInOAuth,
    signOut: logout,
    switchOrganization: switchOrg,
    hasRole,
    hasAnyRole,
    getPrimaryRole,
    refreshSession,
  } = useAuth()

  return (
    <div>
      <div data-testid="session">
        {session ? 'authenticated' : 'unauthenticated'}
      </div>

      <div data-testid="loading">{String(isLoading)}</div>
      <div data-testid="error">{error || 'none'}</div>

      <button onClick={() => signIn('test@example.com', 'password')}>
        Sign In
      </button>

      <button onClick={() => signInOAuth('google')}>
        Google
      </button>

      <button onClick={() => logout()}>
        Sign Out
      </button>

      <button onClick={() => switchOrg('org-1')}>
        Switch Org
      </button>

      <div data-testid="has-role-creator">
        {String(hasRole('creator'))}
      </div>

      <div data-testid="has-any-role">
        {String(hasAnyRole(['creator', 'owner']))}
      </div>

      <div data-testid="primary-role">
        {getPrimaryRole() || 'none'}
      </div>

      <button onClick={refreshSession}>Refresh</button>
    </div>
  )
}

const authenticatedSession = {
  user: { id: 'user-1' },
  currentRoles: ['creator'],
  isLoading: false,
  error: null,
} as any

function renderAuthProvider() {
  return render(
    <AuthProvider>
      <TestComponent />
    </AuthProvider>
  )
}

describe('AuthProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks()

    mockedInitializeSession.mockResolvedValue(authenticatedSession)

    mockedOnAuthStateChange.mockReturnValue({
      unsubscribe: vi.fn(),
    } as any)

    mockedSubscribeToSession.mockImplementation((listener: any) => {
      listener(authenticatedSession)
      return () => {}
    })
  })

  afterEach(() => {
    cleanup()
  })

  it('initializes session on mount', async () => {
    const { unmount } = renderAuthProvider()

    await waitFor(() => {
      expect(screen.getByTestId('loading')).toHaveTextContent('false')
    })

    expect(screen.getByTestId('session')).toHaveTextContent('authenticated')
    unmount()
  })

  it('shows loading state during initialization', () => {
    mockedInitializeSession.mockImplementation(
      () => new Promise(() => {})
    )

    mockedSubscribeToSession.mockImplementation(() => () => {})

    const { unmount } = renderAuthProvider()

    expect(screen.getByTestId('loading')).toHaveTextContent('true')
    unmount()
  })

  it('handles initialization error', async () => {
    mockedInitializeSession.mockRejectedValue(new Error('Auth failed'))
    mockedSubscribeToSession.mockImplementation(() => () => {})

    const { unmount } = renderAuthProvider()

    await waitFor(() => {
      expect(screen.getByTestId('error')).toHaveTextContent('Auth failed')
    })

    expect(screen.getByTestId('session')).toHaveTextContent('unauthenticated')
    unmount()
  })

  it('surfaces auth listener initialization failures instead of throwing from the effect', async () => {
    mockedInitializeSession.mockRejectedValue(new Error('Supabase configuration is missing'));
    mockedOnAuthStateChange.mockImplementation(() => {
      throw new Error('Supabase configuration is missing');
    });
    mockedSubscribeToSession.mockImplementation(() => () => {});

    const { unmount } = renderAuthProvider();
    await waitFor(() => {
      expect(screen.getByTestId('error')).toHaveTextContent('Supabase configuration is missing');
      expect(screen.getByTestId('loading')).toHaveTextContent('false');
    });
    unmount();
  });

  it('does not independently update session from onAuthStateChange callback', async () => {
    const subscribeToSessionCalls: any[] = []

    mockedOnAuthStateChange.mockImplementation((callback: any) => {
      queueMicrotask(() => {
        callback('SIGNED_IN', { user: { id: 'user-2' } })
      })

      return { unsubscribe: vi.fn() } as any
    })

    mockedSubscribeToSession.mockImplementation((listener: any) => {
      subscribeToSessionCalls.push(listener)
      listener(authenticatedSession)
      return () => {}
    })

    const { unmount } = renderAuthProvider()

    await waitFor(() => {
      expect(screen.getByTestId('session')).toHaveTextContent('authenticated')
    })

    await act(async () => {
      await Promise.resolve()
    })

    expect(subscribeToSessionCalls.length).toBeGreaterThan(0)
    unmount()
  })

  it('provides signInWithEmail function', async () => {
    vi.mocked(signInWithEmail).mockResolvedValue({ error: null } as any)

    const { unmount } = renderAuthProvider()

    await waitFor(() => {
      expect(screen.getByTestId('loading')).toHaveTextContent('false')
    })

    await act(async () => {
      screen.getByText('Sign In').click()
    })

    expect(signInWithEmail).toHaveBeenCalledWith(
      'test@example.com',
      'password'
    )
    unmount()
  })

  it('provides signOut function', async () => {
    vi.mocked(signOut).mockResolvedValue({ error: null } as any)

    const { unmount } = renderAuthProvider()

    await waitFor(() => {
      expect(screen.getByTestId('loading')).toHaveTextContent('false')
    })

    await act(async () => {
      screen.getByText('Sign Out').click()
    })

    expect(signOut).toHaveBeenCalled()
    unmount()
  })

  it('provides switchOrganization function', async () => {
    vi.mocked(switchOrganization).mockResolvedValue({ error: null } as any)

    const { unmount } = renderAuthProvider()

    await waitFor(() => {
      expect(screen.getByTestId('loading')).toHaveTextContent('false')
    })

    await act(async () => {
      screen.getByText('Switch Org').click()
    })

    expect(switchOrganization).toHaveBeenCalledWith('org-1')
    unmount()
  })

  it('provides role checking functions', async () => {
    mockedInitializeSession.mockResolvedValue({
      user: { id: 'user-1' },
      currentRoles: ['creator', 'manager'],
      isLoading: false,
      error: null,
    } as any)

    const { unmount } = renderAuthProvider()

    await waitFor(() => {
      expect(screen.getByTestId('loading')).toHaveTextContent('false')
    })

    expect(screen.getByTestId('has-role-creator')).toHaveTextContent('true')
    expect(screen.getByTestId('has-any-role')).toHaveTextContent('true')
    expect(screen.getByTestId('primary-role')).toHaveTextContent('manager')
    unmount()
  })
})

describe('AuthProvider async action failures', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedInitializeSession.mockResolvedValue(authenticatedSession);
    mockedOnAuthStateChange.mockReturnValue({ unsubscribe: vi.fn() } as any);
    mockedSubscribeToSession.mockImplementation((listener: any) => {
      listener(authenticatedSession);
      return () => {};
    });
  });

  it('surfaces unexpected sign-in failures without leaving the UI loading', async () => {
    vi.mocked(signInWithEmail).mockRejectedValue(new Error('Network unavailable'));

    const { unmount } = renderAuthProvider();
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));

    await act(async () => {
      screen.getByText('Sign In').click();
    });

    await waitFor(() => {
      expect(screen.getByTestId('error')).toHaveTextContent('Network unavailable');
      expect(screen.getByTestId('loading')).toHaveTextContent('false');
    });
    unmount();
  });
});

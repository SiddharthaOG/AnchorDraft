/** Authentication service for login, logout, and session management. */

import { getSupabaseClient } from '../../lib/supabase'
import type { SessionUser, AppRole } from './types'
import { resolveUserContext } from './userRole'

const supabase = getSupabaseClient()

/** Current session state (internal). */
let currentSession: SessionUser | null = null
let sessionListeners: Array<(session: SessionUser | null) => void> = []

/** Invalidates asynchronous session builds when a newer auth transition occurs. */
let authGeneration = 0

function bumpGeneration(): number {
  authGeneration += 1
  return authGeneration
}

function getCurrentGeneration(): number {
  return authGeneration
}

function notifyListeners(): void {
  sessionListeners.forEach((listener) => listener(currentSession))
}

/** Subscribe to session changes. */
export function subscribeToSession(
  listener: (session: SessionUser | null) => void,
): () => void {
  sessionListeners.push(listener)
  listener(currentSession)

  return () => {
    const index = sessionListeners.indexOf(listener)
    if (index >= 0) sessionListeners.splice(index, 1)
  }
}

/** Get current session state. */
export function getSession(): SessionUser | null {
  return currentSession
}

/** Initialize session from Supabase auth state. */
export async function initializeSession(): Promise<SessionUser | null> {
  const generation = bumpGeneration()

  const {
    data: { session },
    error,
  } = await supabase.auth.getSession()

  // A newer auth transition may have happened while getSession was pending.
  if (generation !== getCurrentGeneration()) {
    return getSession()
  }

  if (error) {
    console.error('Failed to get Supabase session:', error)

    currentSession = null
    notifyListeners()

    throw new Error(
      `Authentication initialization failed: ${error.message}`,
    )
  }

  if (!session?.user) {
    currentSession = null
    notifyListeners()
    return null
  }

  const builtSession = await buildSessionFromUser(session.user)

  // Critical: the generation may have changed while building the session.
  if (generation !== getCurrentGeneration()) {
    return getSession()
  }

  currentSession = builtSession
  notifyListeners()

  return currentSession
}

/** Build full session state from auth user. */
async function buildSessionFromUser(user: {
  id: string
  email?: string
  user_metadata: Record<string, unknown>
  app_metadata: Record<string, unknown>
  aud: string
  created_at: string
}): Promise<SessionUser> {
  try {
    const context = await resolveUserContext(user.id)
    const profile = await fetchUserProfileSafe(user.id)

    return {
      user: {
        id: user.id,
        email: user.email || '',
        user_metadata: user.user_metadata,
        app_metadata: user.app_metadata,
        aud: user.aud,
        created_at: user.created_at,
      },
      profile,
      memberships: context.memberships,
      organizations: context.organizations,
      currentOrgId: context.currentOrgId,
      currentOrgName: context.currentOrgName,
      currentRoles: context.currentRoles,
      isLoading: false,
      error: null,
    }
  } catch (error) {
    console.error('Failed to build session:', error)

    return {
      user: {
        id: user.id,
        email: user.email || '',
        user_metadata: user.user_metadata,
        app_metadata: user.app_metadata,
        aud: user.aud,
        created_at: user.created_at,
      },
      profile: null,
      memberships: [],
      organizations: [],
      currentOrgId: null,
      currentOrgName: null,
      currentRoles: [],
      isLoading: false,
      error:
        error instanceof Error
          ? error.message
          : 'Failed to load user context',
    }
  }
}

/** Fetch user profile with error handling. */
async function fetchUserProfileSafe(userId: string) {
  try {
    const { data, error } = await getSupabaseClient()
      .from('profiles')
      .select('user_id, display_name, created_at')
      .eq('user_id', userId)
      .single()

    if (error && error.code !== 'PGRST116') {
      console.warn('Failed to fetch profile:', error.message)
    }

    return data
  } catch {
    return null
  }
}

/** Sign in with email and password. */
export async function signInWithEmail(
  email: string,
  password: string,
): Promise<{ error: string | null }> {
  const { error } = await supabase.auth.signInWithPassword({
    email,
    password,
  })

  if (error) {
    return { error: error.message }
  }

  try {
    await initializeSession()
    return { error: null }
  } catch (err) {
    return {
      error:
        err instanceof Error
          ? err.message
          : 'Authentication initialization failed',
    }
  }
}

/** Sign in with OAuth provider (Google, GitHub, etc.). */
export async function signInWithOAuth(
  provider: 'google' | 'github',
): Promise<{ error: string | null }> {
  const { error } = await supabase.auth.signInWithOAuth({
    provider,
    options: {
      redirectTo: `${window.location.origin}/auth/callback`,
    },
  })

  return { error: error?.message || null }
}

/** Sign out the current user. */
export async function signOut(): Promise<{ error: string | null }> {
  const { error } = await supabase.auth.signOut()

  if (error) {
    return { error: error.message }
  }

  // Invalidate pending initialization and auth-event session builds.
  bumpGeneration()

  currentSession = null
  notifyListeners()

  return { error: null }
}

/** Get the current access token for API calls. */
export async function getAccessToken(): Promise<string | null> {
  const {
    data: { session },
  } = await supabase.auth.getSession()

  return session?.access_token || null
}

/** Listen for auth state changes. */
export function onAuthStateChange(
  callback: (
    event: string,
    session: { user: { id: string } | null } | null,
  ) => void,
): { unsubscribe: () => void } {
  let mounted = true

  const {
    data: { subscription },
  } = supabase.auth.onAuthStateChange((event, session) => {
    if (!mounted) return

    // Keep the external callback synchronous.
    callback(event, session)

    // Every auth event invalidates any older asynchronous session build.
    const generation = bumpGeneration()

    queueMicrotask(async () => {
      if (!mounted || generation !== getCurrentGeneration()) {
        return
      }

      try {
        let nextSession: SessionUser | null = currentSession

        if (event === 'SIGNED_IN' && session?.user) {
          nextSession = await buildSessionFromUser(session.user)
        } else if (event === 'SIGNED_OUT') {
          nextSession = null
        } else if (event === 'TOKEN_REFRESHED' && session?.user) {
          nextSession = await buildSessionFromUser(session.user)
        } else {
          return
        }

        // Critical: don't apply an older build after a newer auth event.
        if (!mounted || generation !== getCurrentGeneration()) {
          return
        }

        currentSession = nextSession
        notifyListeners()
      } catch (err) {
        console.error(
          'Failed to rebuild session after auth state change:',
          err,
        )
      }
    })
  })

  return {
    unsubscribe: () => {
      mounted = false
      subscription.unsubscribe()
    },
  }
}

/** Switch the current organization. */
export async function switchOrganization(
  orgId: string,
): Promise<{ error: string | null }> {
  if (!currentSession) {
    return { error: 'No active session' }
  }

  const membership = currentSession.memberships.find(
    (m) => m.org_id === orgId,
  )

  if (!membership) {
    return { error: 'Not a member of this organization' }
  }

  const org = currentSession.organizations.find(
    (o) => o.id === orgId,
  )

  if (!org) {
    return { error: 'Organization not found' }
  }

  currentSession = {
    ...currentSession,
    currentOrgId: orgId,
    currentOrgName: org.name,
    currentRoles: membership.roles,
  }

  try {
    localStorage.setItem('anchordraft_current_org_id', orgId)
  } catch {
    // Ignore localStorage errors.
  }

  notifyListeners()

  return { error: null }
}

/** Check if current user has a role in the current organization. */
export function hasCurrentRole(role: string): boolean {
  if (!currentSession) return false
  return currentSession.currentRoles.includes(role as AppRole)
}

/** Check if current user has any of the specified roles. */
export function hasAnyCurrentRole(roles: string[]): boolean {
  const session = currentSession
  if (!session) return false

  return roles.some((role) =>
    session.currentRoles.includes(role as AppRole),
  )
}

/** Get the primary role for display. */
export function getCurrentPrimaryRole(): string | null {
  const session = currentSession
  if (!session) return null

  const priority: AppRole[] = [
    'owner',
    'manager',
    'reviewer',
    'creator',
  ]

  for (const role of priority) {
    if (session.currentRoles.includes(role)) {
      return role
    }
  }

  return session.currentRoles[0] || null
}
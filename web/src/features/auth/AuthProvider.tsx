/** AuthProvider - React context for authentication state. */

import { createContext, useContext, useEffect, useState, useCallback, ReactNode } from 'react';
import { initializeSession, onAuthStateChange, subscribeToSession } from './authService';
import type { SessionUser } from './types';

interface AuthContextValue {
  session: SessionUser | null;
  isLoading: boolean;
  error: string | null;
  signInWithEmail: (email: string, password: string) => Promise<{ error: string | null }>;
  signInWithOAuth: (provider: 'google' | 'github') => Promise<{ error: string | null }>;
  signOut: () => Promise<{ error: string | null }>;
  switchOrganization: (orgId: string) => Promise<{ error: string | null }>;
  hasRole: (role: string) => boolean;
  hasAnyRole: (roles: string[]) => boolean;
  getPrimaryRole: () => string | null;
  refreshSession: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/** AuthProvider component - wraps the application and provides auth state. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<SessionUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Initialize session on mount
  useEffect(() => {
    let mounted = true;

    async function init() {
      try {
        setIsLoading(true);
        const initialSession = await initializeSession();
        if (mounted) {
          setSession(initialSession);
          setError(initialSession?.error || null);
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err.message : 'Failed to initialize session');
          setSession(null);
        }
      } finally {
        if (mounted) setIsLoading(false);
      }
    }

    init();

    // Subscribe to auth state changes - only notify, don't set session
    // The authoritative session updates come through subscribeToSession
    const { unsubscribe: unsubscribeAuth } = onAuthStateChange((_event, _newSession) => {
      if (!mounted) return;

      // Only notify the callback about the auth event
      // Actual session updates come through subscribeToSession
    });

    // Subscribe to session changes from auth service - this is the authoritative path
    const unsubscribeSession = subscribeToSession(newSession => {
      if (mounted) {
        setSession(newSession);
      }
    });

    return () => {
      mounted = false;
      unsubscribeAuth();
      unsubscribeSession();
    };
  }, []);

  const signInWithEmail = useCallback(async (email: string, password: string) => {
    setError(null);
    setIsLoading(true);
    try {
      const { error } = await (await import('./authService')).signInWithEmail(email, password);
      if (error) setError(error);
      return { error };
    } finally {
      setIsLoading(false);
    }
  }, []);

  const signInWithOAuth = useCallback(async (provider: 'google' | 'github') => {
    setError(null);
    setIsLoading(true);
    try {
      const { error } = await (await import('./authService')).signInWithOAuth(provider);
      if (error) setError(error);
      return { error };
    } finally {
      setIsLoading(false);
    }
  }, []);

  const signOut = useCallback(async () => {
    setError(null);
    setIsLoading(true);
    try {
      const { error } = await (await import('./authService')).signOut();
      if (error) setError(error);
      return { error };
    } finally {
      setIsLoading(false);
    }
  }, []);

  const switchOrganization = useCallback(async (orgId: string) => {
    setError(null);
    try {
      const { error } = await (await import('./authService')).switchOrganization(orgId);
      if (error) setError(error);
      return { error };
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to switch organization';
      setError(message);
      return { error: message };
    }
  }, []);

  const hasRole = useCallback((role: string) => {
    if (!session) return false;
    return session.currentRoles.includes(role as any);
  }, [session]);

  const hasAnyRole = useCallback((roles: string[]) => {
    if (!session) return false;
    return roles.some(role => session.currentRoles.includes(role as any));
  }, [session]);

  const getPrimaryRole = useCallback(() => {
    if (!session) return null;
    const priority = ['owner', 'manager', 'reviewer', 'creator'] as const;
    for (const role of priority) {
      if (session.currentRoles.includes(role)) return role;
    }
    return session.currentRoles[0] || null;
  }, [session]);

  const refreshSession = useCallback(async () => {
    const newSession = await initializeSession();
    setSession(newSession);
    setError(newSession?.error || null);
  }, []);

  const value: AuthContextValue = {
    session,
    isLoading,
    error,
    signInWithEmail,
    signInWithOAuth,
    signOut,
    switchOrganization,
    hasRole,
    hasAnyRole,
    getPrimaryRole,
    refreshSession,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/** Hook to access auth context. */
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
/** OAuth callback page - handles Supabase auth redirect. */

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { initializeSession } from './authService';
import { LoadingScreen } from '../../components/LoadingScreen';

export function AuthCallback() {
  const navigate = useNavigate();
  const [isProcessing, setIsProcessing] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    let redirectTimer: ReturnType<typeof setTimeout> | null = null;

    async function handleCallback() {
      try {
        // Wait for Supabase to process the auth callback and establish session
        // The session may already be available from the redirect, but we ensure it's fully initialized
        const newSession = await initializeSession();

        if (!mounted) return;

        if (newSession) {
          // Successfully authenticated - redirect to dashboard
          navigate('/', { replace: true });
        } else {
          // No session established - redirect to login with error
          setError('Authentication failed. Please try again.');
          redirectTimer = setTimeout(() => navigate('/login', { replace: true }), 3000);
        }
      } catch (err) {
        if (!mounted) return;
        const message = err instanceof Error ? err.message : 'Authentication callback failed';
        setError(message);
        redirectTimer = setTimeout(() => navigate('/login', { replace: true }), 3000);
      } finally {
        if (mounted) {
          setIsProcessing(false);
        }
      }
    }

    handleCallback();

    return () => {
      mounted = false;
      if (redirectTimer) {
        clearTimeout(redirectTimer);
      }
    };
  }, [navigate]);

  if (isProcessing) {
    return (
      <LoadingScreen message="Completing authentication..." />
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="w-full max-w-md bg-white rounded-lg shadow p-6 text-center">
          <div className="w-16 h-16 text-red-400 mx-auto mb-4">
            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h1 className="text-xl font-bold text-gray-900 mb-2">Authentication Failed</h1>
          <p className="text-gray-600 mb-4">{error}</p>
          <p className="text-sm text-gray-500">Redirecting to login...</p>
        </div>
      </div>
    );
  }

  return null;
}

export default AuthCallback;
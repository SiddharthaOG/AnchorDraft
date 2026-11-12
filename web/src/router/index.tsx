/** Application routing configuration. */

import React from 'react';
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom';
import { useAuth } from '../features/auth/AuthProvider';
import Layout from '../components/Layout';
import { CreatorLanding } from '../features/contents/CreatorLanding';
import { ContentCreate } from '../features/contents/ContentCreate';
import { ContentDetail } from '../features/contents/ContentDetail';
import { ManagerLanding } from '../features/approvals/ManagerLanding';
import { ReviewerLanding } from '../features/findings/ReviewerLanding';
import { OwnerLanding } from '../features/kits/OwnerLanding';
import { ConfidentialitySettings } from '../features/kits/ConfidentialitySettings';
import { KitList } from '../features/kits/KitList';
import { KitDetail } from '../features/kits/KitDetail';
import { InsightsLanding } from '../features/insights/InsightsLanding';
import { NoAccess } from '../components/NoAccess';
import { LoadingScreen } from '../components/LoadingScreen';
import { AuthCallback } from '../features/auth/AuthCallback';

/** Protected route wrapper - requires authentication. */
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { session, isLoading } = useAuth();

  if (isLoading) return <LoadingScreen message="Loading authentication..." />;
  if (!session) return <Navigate to="/login" replace />;

  return children;
}

/** Role-based route wrapper. */
function RoleRoute({ allowedRoles, children }: { allowedRoles: string[]; children: React.ReactNode }) {
  const { hasAnyRole } = useAuth();

  if (!hasAnyRole(allowedRoles)) {
    return <NoAccess requiredRoles={allowedRoles} />;
  }

  return children;
}

/** Public route - redirects authenticated users to dashboard. */
function PublicRoute({ children }: { children: React.ReactNode }) {
  const { session, isLoading } = useAuth();

  if (isLoading) return <LoadingScreen message="Loading..." />;
  if (session) return <Navigate to="/" replace />;

  return children;
}

/** Login page component. */
function LoginPage() {
  const { signInWithEmail, signInWithOAuth, isLoading, error } = useAuth();
  const [email, setEmail] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [isSubmitting, setIsSubmitting] = React.useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await signInWithEmail(email, password);
    } finally {
      setIsSubmitting(false);
    }
  };

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
                <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.11.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61-.546-1.387-1.333-1.756-1.333-1.756-1.09-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.776.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
              </svg>
              GitHub
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Root layout route - renders protected Layout with Outlet. */
function RootLayout({ children: _children }: { children?: React.ReactNode }) {
  return (
    <ProtectedRoute>
      <Layout />
    </ProtectedRoute>
  );
}

/** Main application routes. */
export const router = createBrowserRouter([
  // Public routes (no Layout wrapper)
  {
    path: '/login',
    element: (
      <PublicRoute>
        <LoginPage />
      </PublicRoute>
    ),
  },
  {
    path: '/auth/callback',
    element: (
      <PublicRoute>
        <AuthCallback />
      </PublicRoute>
    ),
  },
  // Protected application routes (Layout wrapper applied)
  {
    path: '/',
    element: <RootLayout />,
    children: [
      // Role-aware dashboard: each role lands on its own workspace.
      {
        index: true,
        element: (
          <RoleRoute allowedRoles={['creator', 'manager', 'reviewer', 'owner']}>
            <RoleDashboard />
          </RoleRoute>
        ),
      },
      // Content creation
      {
        path: 'contents/new',
        element: (
          <RoleRoute allowedRoles={['creator', 'manager', 'reviewer', 'owner']}>
            <ContentCreate />
          </RoleRoute>
        ),
      },
      // Content detail and workflow
      {
        path: 'contents/:contentId',
        element: (
          <RoleRoute allowedRoles={['creator', 'manager', 'reviewer', 'owner']}>
            <ContentDetail />
          </RoleRoute>
        ),
      },
      // Owner dashboard
      {
        path: 'owner',
        element: (
          <RoleRoute allowedRoles={['owner']}>
            <OwnerLanding />
          </RoleRoute>
        ),
      },
      {
        path: 'owner/confidentiality',
        element: (
          <RoleRoute allowedRoles={['owner']}>
            <ConfidentialitySettings />
          </RoleRoute>
        ),
      },
      // Brand Kits management
      {
        path: 'kits',
        element: (
          <RoleRoute allowedRoles={['owner']}>
            <KitList />
          </RoleRoute>
        ),
      },
      {
        path: 'kits/:kitId',
        element: (
          <RoleRoute allowedRoles={['owner']}>
            <KitDetail />
          </RoleRoute>
        ),
      },
      // Manager routes
      {
        path: 'approvals',
        element: (
          <RoleRoute allowedRoles={['manager', 'owner']}>
            <ManagerLanding />
          </RoleRoute>
        ),
      },
      // Reviewer routes
      {
        path: 'review',
        element: (
          <RoleRoute allowedRoles={['reviewer', 'owner']}>
            <ReviewerLanding />
          </RoleRoute>
        ),
      },
      // Insights routes (Owner, Manager, Reviewer)
      {
        path: 'insights',
        element: (
          <RoleRoute allowedRoles={['owner', 'manager', 'reviewer']}>
            <InsightsLanding />
          </RoleRoute>
        ),
      },
    ],
  },
]);

/** Router wrapper component. */
export function AppRouter() {
  return <RouterProvider router={router} />;
}
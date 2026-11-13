/** Application routing configuration. */
import React from 'react';
import { createBrowserRouter, createMemoryRouter, RouterProvider, Navigate, useRouteError, type RouteObject } from 'react-router-dom';
import { useAuth } from '../features/auth/AuthProvider';
import Layout from '../components/Layout';
const CreatorLanding = React.lazy(() => import('../features/contents/CreatorLanding').then(module => ({ default: module.CreatorLanding })));
const ContentCreate = React.lazy(() => import('../features/contents/ContentCreate').then(module => ({ default: module.ContentCreate })));
const ContentDetail = React.lazy(() => import('../features/contents/ContentDetail').then(module => ({ default: module.ContentDetail })));
const ManagerLanding = React.lazy(() => import('../features/approvals/ManagerLanding').then(module => ({ default: module.ManagerLanding })));
const ReviewerLanding = React.lazy(() => import('../features/findings/ReviewerLanding').then(module => ({ default: module.ReviewerLanding })));
const OwnerLanding = React.lazy(() => import('../features/kits/OwnerLanding').then(module => ({ default: module.OwnerLanding })));
const ConfidentialitySettings = React.lazy(() => import('../features/kits/ConfidentialitySettings').then(module => ({ default: module.ConfidentialitySettings })));
const KitList = React.lazy(() => import('../features/kits/KitList').then(module => ({ default: module.KitList })));
const KitDetail = React.lazy(() => import('../features/kits/KitDetail').then(module => ({ default: module.KitDetail })));
const InsightsLanding = React.lazy(() => import('../features/insights/InsightsLanding').then(module => ({ default: module.InsightsLanding })));
import { NoAccess } from '../components/NoAccess';
import { LoadingScreen } from '../components/LoadingScreen';
import { AuthCallback } from '../features/auth/AuthCallback';

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { session, isLoading } = useAuth();
  if (isLoading) return <LoadingScreen message="Loading authentication..." />;
  if (!session) return <Navigate to="/login" replace />;
  return children;
}
function RoleRoute({ allowedRoles, children }: { allowedRoles: string[]; children: React.ReactNode }) {
  const { hasAnyRole } = useAuth();
  if (!hasAnyRole(allowedRoles)) return <NoAccess requiredRoles={allowedRoles} />;
  return children;
}
function PublicRoute({ children }: { children: React.ReactNode }) {
  const { session, isLoading } = useAuth();
  if (isLoading) return <LoadingScreen message="Loading..." />;
  if (session) return <Navigate to="/" replace />;
  return children;
}

/** Visible fallback for route render and lazy-import failures. */
function RouteErrorScreen() {
  const error = useRouteError();

  React.useEffect(() => {
    const details = error instanceof Error
      ? { name: error.name, message: error.message }
      : { error };
    console.error('AnchorDraft route failed to render', details);
  }, [error]);

  return (
    <main className="anchordraft-error-screen" role="alert">
      <div className="anchordraft-error-mark" aria-hidden="true">!</div>
      <p className="anchordraft-eyebrow">ANCHORDRAFT / ROUTE RECOVERY</p>
      <h1>This workspace page could not load.</h1>
      <p>The application encountered a page error. Reload the workspace to try again.</p>
      <button type="button" onClick={() => window.location.reload()}>Reload workspace</button>
    </main>
  );
}
function LoginPage() {
  const { signInWithEmail, signInWithOAuth, isLoading, error } = useAuth();
  const [email, setEmail] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault(); setIsSubmitting(true);
    try { await signInWithEmail(email, password); } finally { setIsSubmitting(false); }
  };
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-white rounded-lg shadow p-6">
        <h1 className="text-2xl font-bold text-gray-900 mb-6 text-center">Sign in to AnchorDraft</h1>
        {error && <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">{error}</div>}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div><label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">Email</label><input id="email" type="email" value={email} onChange={e => setEmail(e.target.value)} required className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent" placeholder="you@example.com" /></div>
          <div><label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1">Password</label><input id="password" type="password" value={password} onChange={e => setPassword(e.target.value)} required className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent" placeholder="••••••••" /></div>
          <button type="submit" disabled={isSubmitting || isLoading} className="w-full py-2 px-4 bg-primary text-white rounded-lg font-medium hover:bg-primary-dark focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed">{isSubmitting ? 'Signing in...' : 'Sign in with email'}</button>
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
              className="inline-flex items-center justify-center gap-2 py-2 px-4 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <svg aria-hidden="true" focusable="false" className="h-5 w-5 shrink-0" viewBox="0 0 48 48">
                <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5Z" />
                <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.9c-.58 2.96-2.25 5.48-4.73 7.18l7.62 5.91c4.45-4.11 7.19-10.16 7.19-17.56Z" />
                <path fill="#FBBC05" d="M10.53 28.59A14.4 14.4 0 0 1 9.75 24c0-1.59.27-3.13.76-4.59l-7.98-6.19A23.9 23.9 0 0 0 0 24c0 3.87.93 7.52 2.56 10.78l7.97-6.19Z" />
                <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.9-5.89l-7.62-5.91c-2.12 1.42-4.83 2.27-8.28 2.27-6.26 0-11.57-4.22-13.47-9.91l-7.97 6.19C6.51 42.62 14.62 48 24 48Z" />
              </svg>
              <span>Google</span>
            </button>
            <button
              type="button"
              onClick={() => signInWithOAuth('github')}
              disabled={isLoading || isSubmitting}
              className="inline-flex items-center justify-center gap-2 py-2 px-4 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <svg aria-hidden="true" focusable="false" className="h-5 w-5 shrink-0 text-gray-900" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.11.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61-.546-1.387-1.333-1.756-1.333-1.756-1.09-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.776.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
              </svg>
              <span>GitHub</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
function RoleDashboard() {
  const { session } = useAuth(); const roles = session?.currentRoles ?? [];
  if (roles.includes('owner')) return <OwnerLanding />;
  if (roles.includes('reviewer')) return <ReviewerLanding />;
  if (roles.includes('manager')) return <ManagerLanding />;
  if (roles.includes('creator')) return <CreatorLanding />;
  return <NoAccess requiredRoles={['creator', 'manager', 'reviewer', 'owner']} />;
}
function RootLayout() { return <ProtectedRoute><Layout /></ProtectedRoute>; }

const appRoutes: RouteObject[] = [
  { path: '/login', element: <PublicRoute><LoginPage /></PublicRoute>, errorElement: <RouteErrorScreen /> },
  { path: '/auth/callback', element: <PublicRoute><AuthCallback /></PublicRoute>, errorElement: <RouteErrorScreen /> },
  { path: '/', element: <RootLayout />, errorElement: <RouteErrorScreen />, children: [
    { index: true, element: <RoleRoute allowedRoles={['creator', 'manager', 'reviewer', 'owner']}><RoleDashboard /></RoleRoute> },
    { path: 'contents/new', element: <RoleRoute allowedRoles={['creator', 'manager', 'reviewer', 'owner']}><ContentCreate /></RoleRoute> },
    { path: 'contents/:contentId', element: <RoleRoute allowedRoles={['creator', 'manager', 'reviewer', 'owner']}><ContentDetail /></RoleRoute> },
    { path: 'owner', element: <RoleRoute allowedRoles={['owner']}><OwnerLanding /></RoleRoute> },
    { path: 'owner/confidentiality', element: <RoleRoute allowedRoles={['owner']}><ConfidentialitySettings /></RoleRoute> },
    { path: 'kits', element: <RoleRoute allowedRoles={['owner']}><KitList /></RoleRoute> },
    { path: 'kits/:kitId', element: <RoleRoute allowedRoles={['owner']}><KitDetail /></RoleRoute> },
    { path: 'approvals', element: <RoleRoute allowedRoles={['manager', 'owner']}><ManagerLanding /></RoleRoute> },
    // Submitted items opened from the approvals queue use the shared read-only
    // content detail view. Its edit controls remain disabled for submitted content.
    { path: 'approvals/:contentId', element: <RoleRoute allowedRoles={['manager', 'owner']}><ContentDetail /></RoleRoute> },
    { path: 'review', element: <RoleRoute allowedRoles={['reviewer', 'owner']}><ReviewerLanding /></RoleRoute> },
    { path: 'insights', element: <RoleRoute allowedRoles={['owner', 'manager', 'reviewer']}><InsightsLanding /></RoleRoute> },
  ] },
];

export const router = createBrowserRouter(appRoutes);

/** Build the exact production route tree with in-memory history for integration tests. */
export function createMemoryAppRouter(initialEntries: string[] = ['/']) {
  return createMemoryRouter(appRoutes, { initialEntries });
}

export function AppRouter() {
  return <RouterProvider router={router} />;
}

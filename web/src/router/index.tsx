/** Application routing configuration. */
import React from 'react';
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom';
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
        <div className="mt-6"><div className="relative"><div className="absolute inset-0 flex items-center"><div className="w-full border-t border-gray-300" /></div><div className="relative flex justify-center text-sm"><span className="px-2 bg-white text-gray-500">Or continue with</span></div></div>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <button type="button" onClick={() => signInWithOAuth('google')} disabled={isLoading || isSubmitting} className="py-2 px-4 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2">Google</button>
            <button type="button" onClick={() => signInWithOAuth('github')} disabled={isLoading || isSubmitting} className="py-2 px-4 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2">GitHub</button>
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

export const router = createBrowserRouter([
  { path: '/login', element: <PublicRoute><LoginPage /></PublicRoute> },
  { path: '/auth/callback', element: <PublicRoute><AuthCallback /></PublicRoute> },
  { path: '/', element: <RootLayout />, children: [
    { index: true, element: <RoleRoute allowedRoles={['creator', 'manager', 'reviewer', 'owner']}><RoleDashboard /></RoleRoute> },
    { path: 'contents/new', element: <RoleRoute allowedRoles={['creator', 'manager', 'reviewer', 'owner']}><ContentCreate /></RoleRoute> },
    { path: 'contents/:contentId', element: <RoleRoute allowedRoles={['creator', 'manager', 'reviewer', 'owner']}><ContentDetail /></RoleRoute> },
    { path: 'owner', element: <RoleRoute allowedRoles={['owner']}><OwnerLanding /></RoleRoute> },
    { path: 'owner/confidentiality', element: <RoleRoute allowedRoles={['owner']}><ConfidentialitySettings /></RoleRoute> },
    { path: 'kits', element: <RoleRoute allowedRoles={['owner']}><KitList /></RoleRoute> },
    { path: 'kits/:kitId', element: <RoleRoute allowedRoles={['owner']}><KitDetail /></RoleRoute> },
    { path: 'approvals', element: <RoleRoute allowedRoles={['manager', 'owner']}><ManagerLanding /></RoleRoute> },
    { path: 'review', element: <RoleRoute allowedRoles={['reviewer', 'owner']}><ReviewerLanding /></RoleRoute> },
    { path: 'insights', element: <RoleRoute allowedRoles={['owner', 'manager', 'reviewer']}><InsightsLanding /></RoleRoute> },
  ] },
]);
export function AppRouter() { return <RouterProvider router={router} />; }

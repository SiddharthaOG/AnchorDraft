/** Main application layout with navigation and user display. */

import { Outlet, Link, NavLink } from 'react-router-dom';
import { useAuth } from '../features/auth/AuthProvider';

/** Main layout component. */
export function Layout() {
  const { session, signOut, getPrimaryRole, switchOrganization } = useAuth();

  const navigation = [
    { path: '/', label: 'Dashboard', roles: ['creator', 'manager', 'reviewer', 'owner'] },
    { path: '/owner', label: 'Owner Dashboard', roles: ['owner'] },
    { path: '/owner/confidentiality', label: 'Confidentiality', roles: ['owner'] },
    { path: '/kits', label: 'Brand Kits', roles: ['owner'] },
    { path: '/approvals', label: 'Approvals', roles: ['manager', 'owner'] },
    { path: '/review', label: 'Review Queue', roles: ['reviewer', 'owner'] },
    { path: '/insights', label: 'Insights', roles: ['owner', 'manager', 'reviewer'] },
  ];

  const visibleNav = navigation.filter(item => {
    if (!session) return false;
    return session.currentRoles.some((role: string) => item.roles.includes(role));
  });

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center">
              <Link to="/" className="flex items-center space-x-2" aria-label="AnchorDraft Home">
                <svg className="w-8 h-8 text-primary" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span className="text-xl font-bold text-gray-900">AnchorDraft</span>
              </Link>
            </div>

            <nav className="hidden md:flex items-center space-x-6" aria-label="Main navigation">
              {visibleNav.map(item => (
                <NavLink
                  key={item.path}
                  to={item.path}
                  className={({ isActive }) =>
                    `px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                      isActive
                        ? 'bg-primary text-white'
                        : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>

            <div className="md:hidden">
              <button
                type="button"
                className="inline-flex items-center justify-center p-2 rounded-lg text-gray-600 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-primary"
                aria-label="Toggle menu"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              </button>
            </div>
          </div>

          <div className="flex items-center space-x-4">
            {session && (
              <>
                {session.organizations.length > 1 && (
                  <div className="relative hidden sm:block">
                    <select
                      value={session.currentOrgId || ''}
                      onChange={e => switchOrganization(e.target.value)}
                      className="appearance-none bg-white border border-gray-300 rounded-lg py-1.5 px-3 pr-8 text-sm font-medium text-gray-700 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent cursor-pointer"
                      aria-label="Select organization"
                    >
                      {session.organizations.map((org: { id: string; name: string }) => (
                        <option key={org.id} value={org.id}>
                          {org.name}
                        </option>
                      ))}
                    </select>
                    <div className="absolute inset-y-0 right-0 flex items-center pr-2 pointer-events-none">
                      <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                    </div>
                  </div>
                )}

                <div className="flex items-center space-x-3">
                  <div className="hidden sm:block text-right">
                    <p className="text-sm font-medium text-gray-900">
                      {session.profile?.display_name || session.user?.email || 'User'}
                    </p>
                    <p className="text-xs text-gray-500 capitalize">
                      {getPrimaryRole() || 'No role'}
                    </p>
                  </div>

                  <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-white font-medium">
                    {(session.profile?.display_name || session.user?.email || 'U')[0].toUpperCase()}
                  </div>

                  <button
                    onClick={signOut}
                    className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-700 focus:outline-none focus:ring-2 focus:ring-primary"
                    aria-label="Sign out"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                    </svg>
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Outlet />
      </main>
    </div>
  );
}

export default Layout;
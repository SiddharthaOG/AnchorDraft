/** No access / insufficient permissions component. */

import { Link } from 'react-router-dom';
import { useAuth } from '../features/auth/AuthProvider';

interface NoAccessProps {
  requiredRoles?: string[];
}

export function NoAccess({ requiredRoles = [] }: NoAccessProps) {
  const { session, signOut } = useAuth();

  const isAuthenticated = !!session;
  const userRoles = session?.currentRoles || [];
  const required = requiredRoles.length > 0 ? requiredRoles : ['creator', 'manager', 'reviewer', 'owner'];

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-white rounded-lg shadow p-6">
        <div className="text-center mb-6">
          <svg
            className="w-16 h-16 text-gray-300 mx-auto mb-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2h12z"
            />
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
            />
          </svg>
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Access Denied</h1>
        </div>

        <div className="bg-gray-50 rounded-lg p-4 mb-6">
          {isAuthenticated ? (
            <>
              <p className="text-gray-700 mb-3">
                You don't have permission to access this page.
              </p>
              <div className="text-left text-sm">
                <p className="font-medium text-gray-900 mb-2">Your current roles:</p>
                <ul className="space-y-1 text-gray-600">
                  {userRoles.length > 0 ? (
                    userRoles.map((role: string) => (
                      <li key={role} className="flex items-center">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                          {role.charAt(0).toUpperCase() + role.slice(1)}
                        </span>
                      </li>
                    ))
                  ) : (
                    <li className="text-gray-500">No roles assigned</li>
                  )}
                </ul>
                <p className="mt-3 font-medium text-gray-900 mb-2">Required roles:</p>
                <ul className="space-y-1 text-gray-600">
                  {required.map((role: string) => (
                    <li key={role} className="flex items-center">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-primary-light text-primary">
                        {role.charAt(0).toUpperCase() + role.slice(1)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            </>
          ) : (
            <>
              <p className="text-gray-700 mb-4">
                Please sign in to access this page.
              </p>
              <Link
                to="/login"
                className="inline-flex items-center px-4 py-2 bg-primary text-white rounded-lg font-medium hover:bg-primary-dark focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
              >
                Sign in
              </Link>
            </>
          )}
        </div>

        {isAuthenticated && (
          <div className="text-center">
            <button
              onClick={signOut}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              Sign out as {session?.profile?.display_name || session?.user?.email}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default NoAccess;
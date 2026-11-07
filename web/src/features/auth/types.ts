/** Authentication and user role types. */

export type AppRole = 'creator' | 'manager' | 'reviewer' | 'owner';

export interface UserProfile {
  user_id: string;
  display_name: string;
  created_at: string;
}

export interface Membership {
  org_id: string;
  user_id: string;
  roles: AppRole[];
  created_at: string;
}

export interface Organization {
  id: string;
  name: string;
  created_at?: string;
}

export interface AuthUser {
  id: string;
  email: string;
  user_metadata: Record<string, unknown>;
  app_metadata: Record<string, unknown>;
  aud: string;
  created_at: string;
}

export interface SessionUser {
  user: AuthUser | null;
  profile: UserProfile | null;
  memberships: Membership[];
  organizations: Organization[];
  currentOrgId: string | null;
  currentOrgName: string | null;
  currentRoles: AppRole[];
  isLoading: boolean;
  error: string | null;
}

/** Check if user has a specific role in current organization. */
export function hasRole(user: SessionUser | null, role: AppRole): boolean {
  if (!user) return false;
  return user.currentRoles.includes(role);
}

/** Check if user has any of the specified roles. */
export function hasAnyRole(user: SessionUser | null, roles: AppRole[]): boolean {
  if (!user) return false;
  return roles.some(role => user.currentRoles.includes(role));
}

/** Get the highest priority role for display purposes. */
export function getPrimaryRole(roles: AppRole[]): AppRole | null {
  const priority: AppRole[] = ['owner', 'manager', 'reviewer', 'creator'];
  for (const role of priority) {
    if (roles.includes(role)) return role;
  }
  return roles[0] || null;
}
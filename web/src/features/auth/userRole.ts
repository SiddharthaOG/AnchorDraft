/** User membership and role fetching service. */

import { getSupabaseClient } from '../../lib/supabase';
import type { Membership, AppRole, UserProfile } from './types';

const supabase = getSupabaseClient();

/** Fetch all memberships for the current user. */
export async function fetchUserMemberships(userId: string): Promise<Membership[]> {
  const { data, error } = await supabase
    .from('memberships')
    .select('org_id, roles, user_id, created_at')
    .eq('user_id', userId);

  if (error) {
    throw new Error(`Failed to fetch memberships: ${error.message}`);
  }
  return data || [];
}

/** Fetch organization details by ID. */
export async function fetchOrganization(orgId: string): Promise<{ id: string; name: string } | null> {
  const { data, error } = await supabase
    .from('organizations')
    .select('id, name')
    .eq('id', orgId)
    .single();

  if (error) {
    if (error.code === 'PGRST116') return null; // Not found
    throw new Error(`Failed to fetch organization: ${error.message}`);
  }
  return data;
}

/** Fetch user profile. */
export async function fetchUserProfile(userId: string): Promise<UserProfile | null> {
  const { data, error } = await supabase
    .from('profiles')
    .select('user_id, display_name, created_at')
    .eq('user_id', userId)
    .single();

  if (error) {
    if (error.code === 'PGRST116') return null;
    throw new Error(`Failed to fetch profile: ${error.message}`);
  }
  return data;
}

/** Get the user's current organization ID from session storage or first membership. */
export function getStoredOrgId(): string | null {
  try {
    return localStorage.getItem('anchordraft_current_org_id');
  } catch {
    return null;
  }
}

/** Store the user's current organization ID. */
export function setStoredOrgId(orgId: string | null): void {
  try {
    if (orgId) {
      localStorage.setItem('anchordraft_current_org_id', orgId);
    } else {
      localStorage.removeItem('anchordraft_current_org_id');
    }
  } catch {
    // Ignore localStorage errors
  }
}

/** Determine the user's current organization and roles. */
export async function resolveUserContext(userId: string): Promise<{
  memberships: Membership[];
  organizations: Array<{ id: string; name: string }>;
  currentOrgId: string | null;
  currentOrgName: string | null;
  currentRoles: AppRole[];
}> {
  const memberships = await fetchUserMemberships(userId);

  if (memberships.length === 0) {
    return {
      memberships: [],
      organizations: [],
      currentOrgId: null,
      currentOrgName: null,
      currentRoles: [],
    };
  }

  // Fetch organization names for all memberships
  const orgPromises = memberships.map(m => fetchOrganization(m.org_id));
  const organizations = (await Promise.all(orgPromises)).filter((o): o is { id: string; name: string } => o !== null);

  // Determine current org: use stored preference, or first membership
  let currentOrgId = getStoredOrgId();
  const validOrgIds = new Set(memberships.map(m => m.org_id));

  if (!currentOrgId || !validOrgIds.has(currentOrgId)) {
    currentOrgId = memberships[0].org_id;
  }

  const currentOrg = organizations.find(o => o.id === currentOrgId);
  const currentMembership = memberships.find(m => m.org_id === currentOrgId);

  return {
    memberships,
    organizations,
    currentOrgId: currentOrgId || null,
    currentOrgName: currentOrg?.name || null,
    currentRoles: currentMembership?.roles || [],
  };
}
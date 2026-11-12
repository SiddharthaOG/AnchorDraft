import { getSupabaseClient } from './supabase';
import { getEngineUrl } from './data';

export interface ConfidentialityPolicy {
  org_id: string;
  version: number;
  enabled: boolean;
  custom_terms: string[];
  redact_emails: boolean;
  redact_phones: boolean;
  redact_api_keys: boolean;
  redact_jwts: boolean;
  redact_credit_cards: boolean;
}

export type ConfidentialityPolicyUpdate = Omit<ConfidentialityPolicy, 'org_id' | 'version'>;

async function request<T>(method: 'GET' | 'PUT', payload?: ConfidentialityPolicyUpdate): Promise<T> {
  const { data, error } = await getSupabaseClient().auth.getSession();
  const token = data.session?.access_token;
  if (error || !token) throw new Error('Your session has expired. Sign in again.');
  const response = await fetch(`${getEngineUrl()}/v1/organizations/me/confidentiality-policy`, {
    method,
    headers: { Authorization: `Bearer ${token}`, ...(payload ? { 'Content-Type': 'application/json' } : {}) },
    ...(payload ? { body: JSON.stringify(payload) } : {}),
    cache: 'no-store',
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body?.detail?.error?.message || body?.detail?.message || body?.detail || body?.message;
    throw new Error(typeof detail === 'string' ? detail : `Confidentiality settings request failed (${response.status}).`);
  }
  return body as T;
}

export function getConfidentialityPolicy(): Promise<ConfidentialityPolicy> {
  return request<ConfidentialityPolicy>('GET');
}

export function updateConfidentialityPolicy(policy: ConfidentialityPolicyUpdate): Promise<ConfidentialityPolicy> {
  return request<ConfidentialityPolicy>('PUT', policy);
}

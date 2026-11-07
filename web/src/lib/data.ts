/** Data access layer for Supabase queries under RLS. */

import { getSupabaseClient } from './supabase';
import type { SessionUser } from '../features/auth/types';

const supabase = getSupabaseClient();

// ============================================================
// Type definitions matching database schema
// ============================================================

export interface BrandKit {
  id: string;
  org_id: string;
  version: number;
  name: string;
  status: 'draft' | 'active' | 'archived';
  source_kit_id: string | null;
  created_by: string;
  created_at: string;
  activated_at: string | null;
}

export interface Rule {
  id: string;
  org_id: string;
  kit_id: string;
  rule_key: string;
  category: 'tone' | 'terminology' | 'messaging' | 'claim' | 'fact' | 'accessibility';
  title: string;
  guideline_text: string;
  severity: 'low' | 'medium' | 'high';
  check_kind: 'deterministic' | 'llm';
  config: Record<string, unknown> | null;
  needs_reviewer: boolean;
  example_bad: string | null;
  example_good: string | null;
}

export interface ApprovedFact {
  id: string;
  org_id: string;
  kit_id: string;
  fact_key: string;
  statement: string;
  source_note: string;
  valid_until: string | null;
}

export interface Content {
  id: string;
  org_id: string;
  title: string;
  channel: 'linkedin' | 'blog' | 'email' | 'website' | 'other';
  purpose: string;
  status: 'draft' | 'submitted' | 'changes_requested' | 'approved';
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface Revision {
  id: string;
  org_id: string;
  content_id: string;
  version: number;
  parent_revision_id: string | null;
  body: string;
  source: 'manual' | 'accepted_suggestion' | 'import';
  created_by: string;
  created_at: string;
}

export interface Review {
  id: string;
  org_id: string;
  revision_id: string;
  kit_id: string;
  status: 'queued' | 'running' | 'done' | 'failed';
  error: string | null;
  engine_version: string;
  model: string | null;
  prompt_version: string | null;
  llm_status: 'ok' | 'skipped' | 'failed';
  warnings: unknown[];
  llm_findings_raw: number;
  llm_findings_dropped: number;
  validator_stats: Record<string, unknown>;
  requested_by: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface Finding {
  id: string;
  org_id: string;
  review_id: string;
  source: 'deterministic' | 'llm';
  rule_id: string | null;
  fact_id: string | null;
  ref_key: string;
  category: 'tone' | 'terminology' | 'messaging' | 'claim' | 'fact' | 'accessibility';
  severity: 'low' | 'medium' | 'high';
  quote: string;
  start_offset: number;
  end_offset: number;
  explanation: string;
  suggestion: string | null;
  confidence: number | null;
  needs_human: boolean;
  needs_reviewer: boolean;
  created_at: string;
}

export interface FindingWithDecision extends Finding {
  last_action: 'accept' | 'edit' | 'dismiss' | null;
  last_reason: string | null;
  last_edited_text: string | null;
  resulting_revision_id: string | null;
  decided_at: string | null;
}

export interface ContentStats {
  total: number;
  draft: number;
  submitted: number;
  changes_requested: number;
  approved: number;
}

export interface KitStats {
  total_kits: number;
  active_kit: BrandKit | null;
  draft_kits: number;
  total_rules: number;
  total_facts: number;
}

// ============================================================
// Organization context helpers
// ============================================================

export async function getCurrentOrgId(session: SessionUser | null): Promise<string | null> {
  return session?.currentOrgId || null;
}

// ============================================================
// Brand Kit queries
// ============================================================

export async function getActiveKit(orgId: string): Promise<BrandKit | null> {
  const { data, error } = await supabase
    .from('brand_kits')
    .select('*')
    .eq('org_id', orgId)
    .eq('status', 'active')
    .single();

  if (error && error.code !== 'PGRST116') {
    throw new Error(`Failed to fetch active kit: ${error.message}`);
  }
  return data || null;
}

export async function getBrandKits(orgId: string): Promise<BrandKit[]> {
  const { data, error } = await supabase
    .from('brand_kits')
    .select('*')
    .eq('org_id', orgId)
    .order('version', { ascending: false });

  if (error) {
    throw new Error(`Failed to fetch brand kits: ${error.message}`);
  }
  return data || [];
}

export async function getKitRules(kitId: string): Promise<Rule[]> {
  const { data, error } = await supabase
    .from('rules')
    .select('*')
    .eq('kit_id', kitId)
    .order('rule_key', { ascending: true });

  if (error) {
    throw new Error(`Failed to fetch rules: ${error.message}`);
  }
  return data || [];
}

export async function getKitFacts(kitId: string): Promise<ApprovedFact[]> {
  const { data, error } = await supabase
    .from('approved_facts')
    .select('*')
    .eq('kit_id', kitId)
    .order('fact_key', { ascending: true });

  if (error) {
    throw new Error(`Failed to fetch approved facts: ${error.message}`);
  }
  return data || [];
}

export async function getKitStats(orgId: string): Promise<KitStats> {
  const [kits, activeKit] = await Promise.all([
    getBrandKits(orgId),
    getActiveKit(orgId),
  ]);

  let totalRules = 0;
  let totalFacts = 0;

  if (activeKit) {
    const [rules, facts] = await Promise.all([
      getKitRules(activeKit.id),
      getKitFacts(activeKit.id),
    ]);
    totalRules = rules.length;
    totalFacts = facts.length;
  }

  return {
    total_kits: kits.length,
    active_kit: activeKit,
    draft_kits: kits.filter(k => k.status === 'draft').length,
    total_rules: totalRules,
    total_facts: totalFacts,
  };
}

// ============================================================
// Content queries
// ============================================================

export async function getContents(orgId: string, status?: Content['status']): Promise<Content[]> {
  let query = supabase
    .from('contents')
    .select('*')
    .eq('org_id', orgId)
    .order('created_at', { ascending: false });

  if (status) {
    query = query.eq('status', status);
  }

  const { data, error } = await query;

  if (error) {
    throw new Error(`Failed to fetch contents: ${error.message}`);
  }
  return data || [];
}

export async function getContentStats(orgId: string): Promise<ContentStats> {
  const contents = await getContents(orgId);

  return {
    total: contents.length,
    draft: contents.filter(c => c.status === 'draft').length,
    submitted: contents.filter(c => c.status === 'submitted').length,
    changes_requested: contents.filter(c => c.status === 'changes_requested').length,
    approved: contents.filter(c => c.status === 'approved').length,
  };
}

export async function getLatestRevision(contentId: string): Promise<Revision | null> {
  const { data, error } = await supabase
    .from('v_latest_revision')
    .select('*')
    .eq('content_id', contentId)
    .single();

  if (error && error.code !== 'PGRST116') {
    throw new Error(`Failed to fetch latest revision: ${error.message}`);
  }
  return data || null;
}

export async function getRevisions(contentId: string): Promise<Revision[]> {
  const { data, error } = await supabase
    .from('revisions')
    .select('*')
    .eq('content_id', contentId)
    .order('version', { ascending: false });

  if (error) {
    throw new Error(`Failed to fetch revisions: ${error.message}`);
  }
  return data || [];
}

// ============================================================
// Review & Finding queries
// ============================================================

export async function getLatestReviewForRevision(revisionId: string): Promise<Review | null> {
  const { data, error } = await supabase
    .from('reviews')
    .select('*')
    .eq('revision_id', revisionId)
    .order('created_at', { ascending: false })
    .limit(1)
    .single();

  if (error && error.code !== 'PGRST116') {
    throw new Error(`Failed to fetch review: ${error.message}`);
  }
  return data || null;
}

export async function getReview(reviewId: string): Promise<Review | null> {
  const { data, error } = await supabase
    .from('reviews')
    .select('*')
    .eq('id', reviewId)
    .single();

  if (error && error.code !== 'PGRST116') {
    throw new Error(`Failed to fetch review: ${error.message}`);
  }
  return data || null;
}

export async function getFindingsForReview(reviewId: string): Promise<Finding[]> {
  const { data, error } = await supabase
    .from('findings')
    .select('*')
    .eq('review_id', reviewId)
    .order('created_at', { ascending: true });

  if (error) {
    throw new Error(`Failed to fetch findings: ${error.message}`);
  }
  return data || [];
}

export async function getFindingsWithDecisionsForReview(reviewId: string): Promise<FindingWithDecision[]> {
  const { data, error } = await supabase
    .from('v_finding_state')
    .select('*')
    .eq('review_id', reviewId)
    .order('created_at', { ascending: true });

  if (error) {
    throw new Error(`Failed to fetch findings with decisions: ${error.message}`);
  }
  return data || [];
}

export async function getPendingSignoffs(contentId: string): Promise<Array<{
  finding_id: string;
  ref_key: string;
  category: string;
  severity: string;
  quote: string;
  explanation: string;
  needs_human: boolean;
}>> {
  const { data, error } = await supabase
    .from('v_pending_signoffs')
    .select('finding_id, ref_key, category, severity, quote, explanation, needs_human')
    .eq('content_id', contentId);

  if (error) {
    throw new Error(`Failed to fetch pending signoffs: ${error.message}`);
  }
  return data || [];
}

export interface PendingSignoff {
  finding_id: string;
  content_id: string;
  ref_key: string;
  category: string;
  severity: string;
  quote: string;
  explanation: string;
  needs_human: boolean;
}

export async function getPendingSignoffsByOrg(orgId: string): Promise<PendingSignoff[]> {
  const { data, error } = await supabase
    .from('v_pending_signoffs')
    .select('finding_id, content_id, ref_key, category, severity, quote, explanation, needs_human')
    .eq('org_id', orgId);

  if (error) {
    throw new Error(`Failed to fetch pending signoffs: ${error.message}`);
  }
  return data || [];
}

// ============================================================
// Insights queries
// ============================================================

export interface RuleStat {
  org_id: string;
  ref_key: string;
  category: string;
  findings: number;
  dismissed: number;
  acted_on: number;
  dismissal_rate: number;
  last_seen: string;
}

export async function getRuleStats(orgId: string): Promise<RuleStat[]> {
  const { data, error } = await supabase
    .from('v_rule_stats')
    .select('*')
    .eq('org_id', orgId)
    .order('dismissal_rate', { ascending: false });

  if (error) {
    throw new Error(`Failed to fetch rule stats: ${error.message}`);
  }
  return data || [];
}

// ============================================================
// RPC function wrappers
// ============================================================

export interface CreateContentResult {
  content_id: string;
  revision_id: string;
}

export async function createContent(
  orgId: string,
  title: string,
  channel: string,
  purpose: string,
  body: string
): Promise<CreateContentResult> {
  const { data, error } = await supabase.rpc('create_content', {
    _org: orgId,
    _title: title,
    _channel: channel,
    _purpose: purpose,
    _body: body,
  });

  if (error) {
    throw new Error(`Failed to create content: ${error.message}`);
  }
  return data[0] as CreateContentResult;
}

export interface CreateRevisionResult {
  revision_id: string;
  version: number;
}

export async function createRevision(
  contentId: string,
  body: string
): Promise<CreateRevisionResult> {
  const { data, error } = await supabase.rpc('create_revision', {
    _content_id: contentId,
    _body: body,
  });

  if (error) {
    throw new Error(`Failed to create revision: ${error.message}`);
  }
  return data[0] as CreateRevisionResult;
}

export interface RecordDecisionResult {
  decision_id: string;
}

export async function recordDecision(
  findingId: string,
  action: 'accept' | 'edit' | 'dismiss',
  reason?: string,
  editedText?: string
): Promise<RecordDecisionResult> {
  const { data, error } = await supabase.rpc('record_decision', {
    _finding_id: findingId,
    _action: action,
    _reason: reason || null,
    _edited_text: editedText || null,
  });

  if (error) {
    throw new Error(`Failed to record decision: ${error.message}`);
  }
  return data[0] as RecordDecisionResult;
}

export interface ApplyDecisionsResult {
  revision_id: string;
  version: number;
  applied: number;
  skipped: Array<{ decision_id: string; finding_id: string; reason: string }>;
}

export async function applyDecisions(contentId: string): Promise<ApplyDecisionsResult> {
  const { data, error } = await supabase.rpc('apply_decisions', {
    _content_id: contentId,
  });

  if (error) {
    throw new Error(`Failed to apply decisions: ${error.message}`);
  }
  return data[0] as ApplyDecisionsResult;
}

export async function submitContent(contentId: string): Promise<void> {
  const { error } = await supabase.rpc('submit_content', {
    _content_id: contentId,
  });

  if (error) {
    throw new Error(`Failed to submit content: ${error.message}`);
  }
}

export async function requestChanges(contentId: string, note: string): Promise<void> {
  const { error } = await supabase.rpc('request_changes', {
    _content_id: contentId,
    _note: note,
  });

  if (error) {
    throw new Error(`Failed to request changes: ${error.message}`);
  }
}

export async function recordSignoff(
  findingId: string,
  action: 'signoff' | 'reject_claim',
  note?: string
): Promise<void> {
  const { error } = await supabase.rpc('record_signoff', {
    _finding_id: findingId,
    _action: action,
    _note: note || null,
  });

  if (error) {
    throw new Error(`Failed to record signoff: ${error.message}`);
  }
}

export async function approveContent(contentId: string): Promise<void> {
  const { error } = await supabase.rpc('approve_content', {
    _content_id: contentId,
  });

  if (error) {
    throw new Error(`Failed to approve content: ${error.message}`);
  }
}

export interface CloneKitResult {
  kit_id: string;
  version: number;
}

export async function cloneKit(kitId: string): Promise<CloneKitResult> {
  const { data, error } = await supabase.rpc('clone_kit', {
    _kit_id: kitId,
  });

  if (error) {
    throw new Error(`Failed to clone kit: ${error.message}`);
  }
  return data[0] as CloneKitResult;
}

export async function activateKit(kitId: string): Promise<void> {
  const { error } = await supabase.rpc('activate_kit', {
    _kit_id: kitId,
  });

  if (error) {
    throw new Error(`Failed to activate kit: ${error.message}`);
  }
}

// ============================================================
// Review engine API client
// ============================================================

export interface StartReviewRequest {
  revision_id: string;
}

export interface StartReviewResponse {
  review_id: string;
  status: 'queued' | 'running' | 'done' | 'failed';
  deduplicated: boolean;
  kit_id: string;
  kit_version: number;
}

export class ReviewEngineError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly originalError?: Error,
    public readonly reason?: string,
    public readonly retryAfterSeconds?: number,
  ) {
    super(message);
    this.name = 'ReviewEngineError';
  }
}

export async function startReview(revisionId: string): Promise<StartReviewResponse> {
  const token = await getAuthToken();
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 90000);

  try {
    const response = await fetch(`${getEngineUrl()}/v1/reviews`, {
      method: 'POST',
      signal: controller.signal,
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        'X-Request-Id': crypto.randomUUID(),
      },
      body: JSON.stringify({ revision_id: revisionId }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const message = errorData.error?.message || `Review start failed: ${response.status} ${response.statusText}`;
      const reason = errorData.error?.reason;
      const retryAfter = errorData.error?.retry_after_seconds;
      throw new ReviewEngineError(message, response.status, undefined, reason, retryAfter);
    }

    const data = (await response.json()) as StartReviewResponse;

    // Validate response shape
    if (!data.review_id || !data.status || typeof data.deduplicated !== 'boolean' || !data.kit_id || typeof data.kit_version !== 'number') {
      throw new ReviewEngineError('Invalid review start response shape', 500);
    }

    return data;
  } catch (err) {
    if (err instanceof ReviewEngineError) throw err;
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new ReviewEngineError('Review start timeout after 90s', 504, err);
    }
    throw new ReviewEngineError(
      err instanceof Error ? err.message : 'Network error',
      0,
      err instanceof Error ? err : undefined,
    );
  } finally {
    clearTimeout(timeoutId);
  }
}

// Shared auth token getter for engine API calls
async function getAuthToken(): Promise<string> {
  const { data, error } = await supabase.auth.getSession();
  if (error || !data?.session?.access_token) {
    throw new ReviewEngineError('No valid session', 401);
  }
  return data.session.access_token;
}

// ============================================================
// Kit lint API client
// ============================================================

export interface KitLintIssue {
  severity: 'error' | 'warning';
  code: string;
  ref_key: string | null;
  message: string;
}

export interface KitLintStats {
  rules: number;
  facts: number;
  llm_rules: number;
  deterministic_rules: number;
  prompt_chars_estimate: number;
  prompt_chars_cap: number;
}

export interface KitLintResponse {
  ok: boolean;
  issues: KitLintIssue[];
  stats: KitLintStats;
}

export class KitLintError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly originalError?: Error,
  ) {
    super(message);
    this.name = 'KitLintError';
  }
}

function getEngineUrl(): string {
  const url = import.meta.env.VITE_ENGINE_URL;
  if (!url) {
    const isProduction = import.meta.env.PROD || window.location.hostname !== 'localhost';
    if (isProduction) {
      throw new Error(
        'VITE_ENGINE_URL is not configured. Set VITE_ENGINE_URL environment variable to the engine base URL (e.g., https://anchordraft.onrender.com).'
      );
    }
    return 'http://localhost:8000';
  }
  return url;
}

export async function lintKit(kitId: string): Promise<KitLintResponse> {
  const token = await getAuthToken();
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 60000);

  try {
    const response = await fetch(`${getEngineUrl()}/v1/kits/${kitId}/lint`, {
      method: 'POST',
      signal: controller.signal,
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        'X-Request-Id': crypto.randomUUID(),
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const message = errorData.error?.message || `Lint failed: ${response.status} ${response.statusText}`;
      throw new KitLintError(message, response.status);
    }

    const data = (await response.json()) as KitLintResponse;

    // Validate response shape
    if (typeof data.ok !== 'boolean' || !Array.isArray(data.issues) || !data.stats) {
      throw new KitLintError('Invalid lint response shape', 500);
    }

    return data;
  } catch (err) {
    if (err instanceof KitLintError) throw err;
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new KitLintError('Lint request timeout after 60s', 504, err);
    }
    throw new KitLintError(
      err instanceof Error ? err.message : 'Network error',
      0,
      err instanceof Error ? err : undefined,
    );
  } finally {
    clearTimeout(timeoutId);
  }
}

// ============================================================
// Rule mutations (draft kits only, via RLS)
// ============================================================

export interface CreateRuleInput {
  kit_id: string;
  rule_key: string;
  category: Rule['category'];
  title: string;
  guideline_text: string;
  severity: Rule['severity'];
  check_kind: Rule['check_kind'];
  config: Record<string, unknown> | null;
  needs_reviewer: boolean;
  example_bad: string | null;
  example_good: string | null;
}

export async function createRule(input: CreateRuleInput): Promise<Rule> {
  const { data, error } = await supabase
    .from('rules')
    .insert(input)
    .select()
    .single();

  if (error) {
    throw new Error(`Failed to create rule: ${error.message}`);
  }
  return data;
}

export interface UpdateRuleInput {
  rule_key?: string;
  category?: Rule['category'];
  title?: string;
  guideline_text?: string;
  severity?: Rule['severity'];
  check_kind?: Rule['check_kind'];
  config?: Record<string, unknown> | null;
  needs_reviewer?: boolean;
  example_bad?: string | null;
  example_good?: string | null;
}

export async function updateRule(ruleId: string, input: UpdateRuleInput): Promise<Rule> {
  const { data, error } = await supabase
    .from('rules')
    .update(input)
    .eq('id', ruleId)
    .select()
    .single();

  if (error) {
    throw new Error(`Failed to update rule: ${error.message}`);
  }
  return data;
}

export async function deleteRule(ruleId: string): Promise<void> {
  const { error } = await supabase
    .from('rules')
    .delete()
    .eq('id', ruleId);

  if (error) {
    throw new Error(`Failed to delete rule: ${error.message}`);
  }
}

// ============================================================
// Approved fact mutations (draft kits only, via RLS)
// ============================================================

export interface CreateFactInput {
  kit_id: string;
  fact_key: string;
  statement: string;
  source_note: string;
  valid_until: string | null;
}

export async function createFact(input: CreateFactInput): Promise<ApprovedFact> {
  const { data, error } = await supabase
    .from('approved_facts')
    .insert(input)
    .select()
    .single();

  if (error) {
    throw new Error(`Failed to create approved fact: ${error.message}`);
  }
  return data;
}

export interface UpdateFactInput {
  fact_key?: string;
  statement?: string;
  source_note?: string;
  valid_until?: string | null;
}

export async function updateFact(factId: string, input: UpdateFactInput): Promise<ApprovedFact> {
  const { data, error } = await supabase
    .from('approved_facts')
    .update(input)
    .eq('id', factId)
    .select()
    .single();

  if (error) {
    throw new Error(`Failed to update approved fact: ${error.message}`);
  }
  return data;
}

export async function deleteFact(factId: string): Promise<void> {
  const { error } = await supabase
    .from('approved_facts')
    .delete()
    .eq('id', factId);

  if (error) {
    throw new Error(`Failed to delete approved fact: ${error.message}`);
  }
}
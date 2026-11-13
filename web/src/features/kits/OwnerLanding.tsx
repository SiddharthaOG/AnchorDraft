/** Owner (Guideline Owner) landing page - for brand kit management. */

import React, { useEffect, useState, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../features/auth/AuthProvider';
import { LoadingScreen } from '../../components/LoadingScreen';
import {
  getKitStats,
  getKitRules,
  getKitFacts,
  cloneKit,
  type KitStats,
  type BrandKit,
  type Rule,
  type ApprovedFact,
} from '../../lib/data';

interface StatCardProps {
  label: string;
  value: string | number;
  icon: React.ReactNode;
  href?: string;
}

function StatCard({ label, value, icon, href }: StatCardProps) {
  const content = (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500">{label}</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{value}</p>
        </div>
        <div className="p-3 bg-primary-light rounded-lg text-primary">
          {icon}
        </div>
      </div>
      {href && (
        <span className="mt-4 inline-flex items-center text-sm font-medium text-primary">
          View all →
        </span>
      )}
    </div>
  );

  return href ? <Link to={href}>{content}</Link> : content;
}

function DisabledAction({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <div className="p-4 border border-gray-200 rounded-lg bg-gray-50 text-center opacity-60">
      <div className="w-10 h-10 mx-auto text-gray-300 mb-2" aria-hidden="true">
        {children}
      </div>
      <p className="font-medium text-gray-500">{label}</p>
      <p className="text-xs text-gray-400 mt-1">Coming soon</p>
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="bg-red-50 border border-red-200 rounded-lg p-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-red-800">Unable to load data</h3>
          <p className="text-red-600 text-sm mt-1">{message}</p>
        </div>
        <button
          onClick={onRetry}
          className="px-3 py-1.5 bg-red-600 text-white text-sm rounded-lg hover:bg-red-700"
        >
          Retry
        </button>
      </div>
    </div>
  );
}

/** Owner dashboard landing page. */
export function OwnerLanding() {
  const { session, isLoading: authLoading } = useAuth();
  const navigate = useNavigate();
  const [isCreatingKit, setIsCreatingKit] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [kitStats, setKitStats] = useState<KitStats | null>(null);
  const [activeKit, setActiveKit] = useState<BrandKit | null>(null);
  const [rules, setRules] = useState<Rule[]>([]);
  const [facts, setFacts] = useState<ApprovedFact[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Request ID for stale-request protection
  const requestIdRef = useRef(0);

  const loadData = async () => {
    const orgId = session?.currentOrgId;
    if (!orgId) {
      // Clear data immediately when no org selected
      setKitStats(null);
      setActiveKit(null);
      setRules([]);
      setFacts([]);
      setIsLoading(false);
      return;
    }

    const currentRequestId = ++requestIdRef.current;
    setIsLoading(true);
    setError(null);

    try {
      const stats = await getKitStats(orgId);

      // Stale request check
      if (currentRequestId !== requestIdRef.current) return;

      setKitStats(stats);

      if (stats.active_kit) {
        const [kitRules, kitFacts] = await Promise.all([
          getKitRules(stats.active_kit.id),
          getKitFacts(stats.active_kit.id),
        ]);

        // Stale request check after parallel fetches
        if (currentRequestId !== requestIdRef.current) return;

        setActiveKit(stats.active_kit);
        setRules(kitRules);
        setFacts(kitFacts);
      } else {
        // No active kit - clear related data
        setActiveKit(null);
        setRules([]);
        setFacts([]);
      }
    } catch (err) {
      if (currentRequestId !== requestIdRef.current) return;
      setError(err instanceof Error ? err.message : 'Failed to load dashboard data');
    } finally {
      if (currentRequestId === requestIdRef.current) {
        setIsLoading(false);
      }
    }
  };

  const handleCreateBrandKit = async () => {
    if (!activeKit) {
      navigate('/kits');
      return;
    }

    setIsCreatingKit(true);
    setActionError(null);
    try {
      const draft = await cloneKit(activeKit.id);
      navigate(`/kits/${draft.kit_id}`);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Unable to create a draft brand kit.');
    } finally {
      setIsCreatingKit(false);
    }
  };

  // Refetch when orgId changes
  useEffect(() => {
    if (!authLoading && session) {
      loadData();
    }
  }, [authLoading, session, session?.currentOrgId]);

  if (authLoading || !session) {
    return <LoadingScreen message="Loading dashboard..." />;
  }

  if (isLoading) {
    return <LoadingScreen message="Loading brand kit data..." />;
  }

  if (error) {
    return (
      <div className="space-y-8">
        <ErrorState message={error} onRetry={loadData} />
      </div>
    );
  }

  const rulesByCategory = rules.reduce((acc, rule) => {
    if (!acc[rule.category]) acc[rule.category] = [];
    acc[rule.category].push(rule);
    return acc;
  }, {} as Record<string, Rule[]>);

  return (
    <div className="space-y-8">
      {/* Welcome header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          Welcome, {session.profile?.display_name?.split(' ')[0] || 'Guideline Owner'}
        </h1>
        <p className="text-gray-600 mt-1">
          Manage brand kits, rules, and approved facts for your organization.
        </p>
      </div>

      {/* Quick stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          label="Active Kit"
          value={activeKit ? 1 : 0}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2h12z" />
            </svg>
          }
          href="/kits"
        />
        <StatCard
          label="Draft Kits"
          value={kitStats?.draft_kits || 0}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          }
          href="/kits"
        />
        <StatCard
          label="Rules"
          value={kitStats?.total_rules || 0}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
            </svg>
          }
          href="/kits"
        />
        <StatCard
          label="Approved Facts"
          value={kitStats?.total_facts || 0}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
          href="/kits"
        />
      </div>

      {/* Quick actions */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Quick Actions</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <button
            type="button"
            onClick={() => void handleCreateBrandKit()}
            disabled={isCreatingKit}
            className="p-4 border border-gray-200 rounded-lg hover:border-primary hover:bg-gray-50 transition-colors text-center disabled:opacity-60"
          >
            <svg className="w-10 h-10 mx-auto text-gray-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            <p className="font-medium text-gray-900">{isCreatingKit ? 'Creating draft...' : 'Create Brand Kit'}</p>
            <p className="text-sm text-gray-500 mt-1">Clone the active kit into a new draft</p>
          </button>

          <Link
            to="/kits"
            className="p-4 border border-gray-200 rounded-lg hover:border-primary hover:bg-gray-50 transition-colors text-center"
          >
            <svg className="w-10 h-10 mx-auto text-gray-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
            </svg>
            <p className="font-medium text-gray-900">Manage Kits</p>
            <p className="text-sm text-gray-500 mt-1">View and edit kits</p>
          </Link>

          <Link
            to="/kits"
            className="p-4 border border-gray-200 rounded-lg hover:border-primary hover:bg-gray-50 transition-colors text-center"
          >
            <svg className="w-10 h-10 mx-auto text-gray-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p className="font-medium text-gray-900">Lint Kit</p>
            <p className="text-sm text-gray-500 mt-1">Open a draft kit and run its checks</p>
          </Link>
        </div>
        {actionError && <p role="alert" className="mt-3 text-sm text-red-700">{actionError}</p>}
        <div className="mt-4 flex flex-wrap gap-4">
          <Link to="/insights" className="text-sm font-medium text-primary hover:text-primary-dark">
            Open guideline-gap analytics ?
          </Link>
          <Link to="/owner/confidentiality" className="text-sm font-medium text-primary hover:text-primary-dark">
            Confidentiality settings ?
          </Link>
        </div>
      </div>

      {/* Active kit overview */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Active Brand Kit</h2>
          {activeKit && (
            <Link to="/kits" className="text-sm font-medium text-primary hover:text-primary-dark">
              View all →
            </Link>
          )}
        </div>

        {activeKit ? (
          <div className="space-y-6">
            <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
              <div>
                <h3 className="font-semibold text-gray-900">{activeKit.name}</h3>
                <p className="text-sm text-gray-500">Version {activeKit.version} • Activated {new Date(activeKit.activated_at!).toLocaleDateString()}</p>
              </div>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                Active
              </span>
            </div>

            <div>
              <h4 className="font-medium text-gray-900 mb-3">Rules by Category</h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {Object.entries(rulesByCategory).map(([category, catRules]) => (
                  <div key={category} className="p-3 bg-gray-50 rounded-lg">
                    <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{category}</p>
                    <p className="text-2xl font-bold text-gray-900">{catRules.length}</p>
                    <p className="text-xs text-gray-400">
                      {catRules.filter(r => r.check_kind === 'deterministic').length} deterministic, {catRules.filter(r => r.check_kind === 'llm').length} LLM
                    </p>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h4 className="font-medium text-gray-900 mb-3">Approved Facts</h4>
              {facts.length > 0 ? (
                <ul className="divide-y divide-gray-200">
                  {facts.slice(0, 3).map(fact => (
                    <li key={fact.id} className="py-3">
                      <p className="font-medium text-gray-900">{fact.fact_key}</p>
                      <p className="text-sm text-gray-600">{fact.statement}</p>
                      <p className="text-xs text-gray-400">Source: {fact.source_note}</p>
                    </li>
                  ))}
                  {facts.length > 3 && (
                    <li className="py-3 text-center text-sm text-gray-500">
                      +{facts.length - 3} more facts
                    </li>
                  )}
                </ul>
              ) : (
                <p className="text-gray-500 text-center py-4">No approved facts in this kit</p>
              )}
            </div>
          </div>
        ) : (
          <div className="text-center py-8">
            <svg className="w-12 h-12 text-gray-300 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2h12z" />
            </svg>
            <p className="text-gray-500 mb-4">No active brand kit</p>
            <DisabledAction
              label="Create your first brand kit"
            >
              <svg className="w-6 h-6 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
            </DisabledAction>
          </div>
        )}
      </div>

      {/* Guidelines */}
      <div className="bg-gray-50 rounded-lg p-6">
        <h3 className="font-semibold text-gray-900 mb-2">Kit Guidelines</h3>
        <ul className="text-gray-600 text-sm space-y-1">
          <li>• Rules and facts are versioned with each kit — old findings stay explainable</li>
          <li>• Only draft kits can be edited; activate to make it the live standard</li>
          <li>• Use the lint endpoint to check for issues before activating</li>
          <li>• Rules use stable keys (e.g., TERM-01) so insights work across versions</li>
        </ul>
      </div>
    </div>
  );
}

export default OwnerLanding;
/** Reviewer landing page - for sign-off and claim review. */

import React, { useEffect, useState, useRef } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../features/auth/AuthProvider';
import { LoadingScreen } from '../../components/LoadingScreen';
import {
  getContents,
  getContentStats,
  getPendingSignoffs,
  type ContentStats,
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
        <Link
          to={href}
          className="mt-4 inline-flex items-center text-sm font-medium text-primary hover:text-primary-dark"
        >
          View all →
        </Link>
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

function EmptyState({ icon: Icon, title, description }: {
  icon: React.ElementType;
  title: string;
  description: string;
}) {
  return (
    <div className="text-center py-8">
      <Icon className="w-12 h-12 text-gray-300 mx-auto mb-3" aria-hidden="true" />
      <p className="text-gray-500 mb-4">{title}</p>
      <p className="text-sm text-gray-400">{description}</p>
    </div>
  );
}

/** Reviewer dashboard landing page. */
export function ReviewerLanding() {
  const { session, isLoading: authLoading } = useAuth();
  const [stats, setStats] = useState<ContentStats | null>(null);
  const [pendingSignoffs, setPendingSignoffs] = useState<Array<{
    content_id: string;
    finding_id: string;
    ref_key: string;
    category: string;
    severity: string;
    quote: string;
    explanation: string;
    needs_human: boolean;
  }>>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Request ID for stale-request protection
  const requestIdRef = useRef(0);

  const loadData = async () => {
    const orgId = session?.currentOrgId;
    if (!orgId) {
      setStats(null);
      setPendingSignoffs([]);
      setIsLoading(false);
      return;
    }

    const currentRequestId = ++requestIdRef.current;
    setIsLoading(true);
    setError(null);

    try {
      const [allContents, contentStats] = await Promise.all([
        getContents(orgId, 'submitted'),
        getContentStats(orgId),
      ]);

      // Stale request check
      if (currentRequestId !== requestIdRef.current) return;

      setStats(contentStats);

      // Load pending signoffs for each submitted content
      const signoffsPromises = allContents.map(async c => {
        const signoffs = await getPendingSignoffs(c.id);
        return signoffs.map(s => ({ ...s, content_id: c.id }));
      });
      const signoffsResults = await Promise.all(signoffsPromises);
      const allSignoffs = signoffsResults.flat();

      // Stale request check after signoffs fetch
      if (currentRequestId !== requestIdRef.current) return;

      setPendingSignoffs(allSignoffs);
    } catch (err) {
      if (currentRequestId !== requestIdRef.current) return;
      setError(err instanceof Error ? err.message : 'Failed to load dashboard data');
    } finally {
      if (currentRequestId === requestIdRef.current) {
        setIsLoading(false);
      }
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
    return <LoadingScreen message="Loading review data..." />;
  }

  if (error) {
    return (
      <div className="space-y-8">
        <ErrorState message={error} onRetry={loadData} />
      </div>
    );
  }

  // Group signoffs by content for display
  const signoffsByContent = pendingSignoffs.reduce((acc, signoff) => {
    if (!acc[signoff.content_id]) acc[signoff.content_id] = [];
    acc[signoff.content_id].push(signoff);
    return acc;
  }, {} as Record<string, typeof pendingSignoffs>);

  return (
    <div className="space-y-8">
      {/* Welcome header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          Welcome, {session.profile?.display_name?.split(' ')[0] || 'Reviewer'}
        </h1>
        <p className="text-gray-600 mt-1">
          Review findings that need sign-off or claim rejection.
        </p>
      </div>

      {/* Quick stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          label="Pending Sign-offs"
          value={pendingSignoffs.length}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
          href="/review"
        />
        <StatCard
          label="Claims to Reject"
          value={pendingSignoffs.filter(s => s.category === 'claim').length}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          }
          href="/review"
        />
        <StatCard
          label="Completed"
          value={stats?.approved || 0}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
          href="/review"
        />
        <StatCard
          label="Total Reviews"
          value={stats?.submitted || 0}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
            </svg>
          }
          href="/review"
        />
      </div>

      {/* Quick actions */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Quick Actions</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Link
            to="/review"
            className="p-4 border border-gray-200 rounded-lg hover:border-primary hover:bg-gray-50 transition-colors text-center"
          >
            <svg className="w-10 h-10 mx-auto text-gray-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
            </svg>
            <p className="font-medium text-gray-900">Review Queue</p>
            <p className="text-sm text-gray-500 mt-1">Findings awaiting your decision</p>
          </Link>

          <DisabledAction
            label="Review History"
          >
            <svg className="w-10 h-10 mx-auto text-gray-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </DisabledAction>

          <DisabledAction
            label="Claims to Reject"
          >
            <svg className="w-10 h-10 mx-auto text-gray-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
            </svg>
          </DisabledAction>
        </div>
      </div>

      {/* Pending sign-offs queue */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Findings Awaiting Your Sign-off</h2>
          {pendingSignoffs.length > 0 && (
            <Link to="/review" className="text-sm font-medium text-primary hover:text-primary-dark">
              View all →
            </Link>
          )}
        </div>

        {pendingSignoffs.length > 0 ? (
          <div className="space-y-4">
            {Object.entries(signoffsByContent).map(([contentId, signoffs]) => (
              <div key={contentId} className="border border-gray-200 rounded-lg overflow-hidden">
                <div className="p-4 bg-gray-50 border-b border-gray-200">
                  <h3 className="font-medium text-gray-900">
                    Content #{contentId.slice(0, 8)}
                  </h3>
                  <p className="text-sm text-gray-500">{signoffs.length} finding{signoffs.length > 1 ? 's' : ''} awaiting sign-off</p>
                </div>
                <div className="divide-y divide-gray-200">
                  {signoffs.map(signoff => (
                    <Link
                      key={signoff.finding_id}
                      to={`/review/${signoff.finding_id}`}
                      className="block p-4 hover:bg-gray-50 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-2">
                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium
                              {signoff.severity === 'high' && 'bg-red-100 text-red-700'}
                              {signoff.severity === 'medium' && 'bg-yellow-100 text-yellow-700'}
                              {signoff.severity === 'low' && 'bg-gray-100 text-gray-700'}
                            ">
                              {signoff.severity}
                            </span>
                            <span className="text-sm font-medium text-gray-900">{signoff.ref_key}</span>
                            <span className="text-xs text-gray-500 capitalize">{signoff.category}</span>
                            {signoff.needs_human && (
                              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-700">
                                Needs human review
                              </span>
                            )}
                          </div>
                          <p className="text-sm text-gray-600 line-clamp-2">{signoff.explanation}</p>
                          <p className="text-sm text-gray-500 mt-1 italic">"{signoff.quote}"</p>
                        </div>
                        <svg className="w-5 h-5 text-gray-400 flex-shrink-0 mt-1" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                      </div>
                    </Link>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            icon={(props) => (
              <svg {...props} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            )}
            title="No findings awaiting your sign-off"
            description="Findings that need reviewer sign-off will appear here"
          />
        )}
      </div>

      {/* Guidelines */}
      <div className="bg-gray-50 rounded-lg p-6">
        <h3 className="font-semibold text-gray-900 mb-2">Reviewer Actions</h3>
        <ul className="text-gray-600 text-sm space-y-1">
          <li>• <strong>Sign-off</strong> — Approve a finding that requires reviewer validation</li>
          <li>• <strong>Reject Claim</strong> — Reject an unsupported claim with a mandatory note</li>
          <li>• Sign-offs are required for fact findings and rules marked <code>needs_reviewer</code></li>
          <li>• Rejected claims send content back to <strong>Changes Requested</strong> status</li>
        </ul>
      </div>
    </div>
  );
}

export default ReviewerLanding;
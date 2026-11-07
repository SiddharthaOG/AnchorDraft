/** Manager landing page - for approval workflow. */

import React, { useEffect, useState, useRef } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../features/auth/AuthProvider';
import { LoadingScreen } from '../../components/LoadingScreen';
import {
  getContents,
  getContentStats,
  getPendingSignoffsByOrg,
  type Content,
  type ContentStats,
  type PendingSignoff,
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

/** Manager dashboard landing page. */
export function ManagerLanding() {
  const { session, isLoading: authLoading } = useAuth();
  const [contents, setContents] = useState<Content[]>([]);
  const [stats, setStats] = useState<ContentStats | null>(null);
  const [pendingSignoffs, setPendingSignoffs] = useState<PendingSignoff[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Request ID for stale-request protection
  const requestIdRef = useRef(0);

  const loadData = async () => {
    const orgId = session?.currentOrgId;
    if (!orgId) {
      setContents([]);
      setStats(null);
      setPendingSignoffs([]);
      setIsLoading(false);
      return;
    }

    const currentRequestId = ++requestIdRef.current;
    setIsLoading(true);
    setError(null);

    try {
      const [allContents, contentStats, allSignoffs] = await Promise.all([
        getContents(orgId, 'submitted'),
        getContentStats(orgId),
        getPendingSignoffsByOrg(orgId),
      ]);

      // Stale request check
      if (currentRequestId !== requestIdRef.current) return;

      setContents(allContents);
      setStats(contentStats);
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
    return <LoadingScreen message="Loading approval data..." />;
  }

  if (error) {
    return (
      <div className="space-y-8">
        <ErrorState message={error} onRetry={loadData} />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Welcome header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          Welcome, {session.profile?.display_name?.split(' ')[0] || 'Manager'}
        </h1>
        <p className="text-gray-600 mt-1">
          Review submitted content, request changes, and approve final drafts.
        </p>
      </div>

      {/* Quick stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          label="Submitted"
          value={stats?.submitted || 0}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
          href="/approvals"
        />
        <StatCard
          label="Pending Sign-offs"
          value={(Array.isArray(pendingSignoffs) ? pendingSignoffs : []).length}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
            </svg>
          }
          href="/approvals"
        />
        <StatCard
          label="Changes Requested"
          value={stats?.changes_requested || 0}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
            </svg>
          }
          href="/approvals"
        />
        <StatCard
          label="Approved"
          value={stats?.approved || 0}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
          href="/approvals"
        />
      </div>

      {/* Quick actions */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Quick Actions</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Link
            to="/approvals"
            className="p-4 border border-gray-200 rounded-lg hover:border-primary hover:bg-gray-50 transition-colors text-center"
          >
            <svg className="w-10 h-10 mx-auto text-gray-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
            </svg>
            <p className="font-medium text-gray-900">Review Queue</p>
            <p className="text-sm text-gray-500 mt-1">Content awaiting decision</p>
          </Link>

          <DisabledAction
            label="Pending Sign-offs"
          >
            <svg className="w-10 h-10 mx-auto text-gray-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </DisabledAction>

          <DisabledAction
            label="Approval History"
          >
            <svg className="w-10 h-10 mx-auto text-gray-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </DisabledAction>
        </div>
      </div>

      {/* Submitted content queue */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Submitted Content Awaiting Review</h2>
          {contents.length > 0 && (
            <Link to="/approvals" className="text-sm font-medium text-primary hover:text-primary-dark">
              View all →
            </Link>
          )}
        </div>

        {contents.length > 0 ? (
          <div className="divide-y divide-gray-200">
            {contents.map(content => {
              const contentSignoffs = pendingSignoffs.filter(s => s.content_id === content.id);
              return (
                <Link
                  key={content.id}
                  to={`/approvals/${content.id}`}
                  className="block p-4 hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex-1 min-w-0">
                      <h3 className="font-medium text-gray-900 truncate">{content.title}</h3>
                      <div className="flex items-center gap-3 mt-1 text-sm">
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-700">
                          Submitted
                        </span>
                        {contentSignoffs.length > 0 && (
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-700">
                            {contentSignoffs.length} sign-off{contentSignoffs.length > 1 ? 's' : ''} pending
                          </span>
                        )}
                      </div>
                    </div>
                    <svg className="w-5 h-5 text-gray-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </div>
                </Link>
              );
            })}
          </div>
        ) : (
          <EmptyState
            icon={(props) => (
              <svg {...props} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
              </svg>
            )}
            title="No content submitted for review"
            description="Content will appear here when creators submit for approval"
          />
        )}
      </div>

      {/* Guidelines */}
      <div className="bg-gray-50 rounded-lg p-6">
        <h3 className="font-semibold text-gray-900 mb-2">Manager Actions</h3>
        <ul className="text-gray-600 text-sm space-y-1">
          <li>• <strong>Approve</strong> — Final sign-off on submitted content</li>
          <li>• <strong>Request Changes</strong> — Send content back with required notes</li>
          <li>• <strong>Sign-off</strong> — Required for findings flagged as needing reviewer</li>
          <li>• <strong>Reject Claim</strong> — Reject unsupported claims with mandatory note</li>
        </ul>
      </div>
    </div>
  );
}

export default ManagerLanding;
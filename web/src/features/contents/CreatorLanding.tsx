/** Creator landing page - for content creation and review workflow. */

import React, { useEffect, useState, useRef } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../features/auth/AuthProvider';
import { LoadingScreen } from '../../components/LoadingScreen';
import {
  getContents,
  getContentStats,
  type Content,
  type ContentStats,
} from '../../lib/data';

interface StatCardProps {
  label: string;
  value: string | number;
  icon: React.ReactNode;
}

function StatCard({ label, value, icon }: StatCardProps) {
  return (
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
    </div>
  );
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

function EmptyState({ icon: Icon, title, description, action }: {
  icon: React.ElementType;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="text-center py-8">
      <Icon className="w-12 h-12 text-gray-300 mx-auto mb-3" aria-hidden="true" />
      <p className="text-gray-500 mb-4">{title}</p>
      <p className="text-sm text-gray-400 mb-4">{description}</p>
      {action}
    </div>
  );
}

/** Creator dashboard landing page. */
export function CreatorLanding() {
  const { session, isLoading: authLoading } = useAuth();
  const [contents, setContents] = useState<Content[]>([]);
  const [stats, setStats] = useState<ContentStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Request ID for stale-request protection
  const requestIdRef = useRef(0);

  const loadData = async () => {
    const orgId = session?.currentOrgId;
    if (!orgId) {
      setContents([]);
      setStats(null);
      setIsLoading(false);
      return;
    }

    const currentRequestId = ++requestIdRef.current;
    setIsLoading(true);
    setError(null);

    try {
      const [allContents, contentStats] = await Promise.all([
        getContents(orgId),
        getContentStats(orgId),
      ]);

      // Stale request check
      if (currentRequestId !== requestIdRef.current) return;

      setContents(allContents || []);
      setStats(contentStats);
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
    return <LoadingScreen message="Loading content data..." />;
  }

  if (error) {
    return (
      <div className="space-y-8">
        <ErrorState message={error} onRetry={loadData} />
      </div>
    );
  }

  const recentContents = (contents || []).slice(0, 5);

  return (
    <div className="space-y-8">
      {/* Welcome header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          Welcome back, {session.profile?.display_name?.split(' ')[0] || 'Creator'}
        </h1>
        <p className="text-gray-600 mt-1">
          Create content, submit for review, and track your revisions.
        </p>
      </div>

      {/* Quick stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          label="Drafts"
          value={stats?.draft || 0}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          }
        />
        <StatCard
          label="Submitted"
          value={stats?.submitted || 0}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
        />
        <StatCard
          label="In Review"
          value={stats?.changes_requested || 0}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
            </svg>
          }
        />
        <StatCard
          label="Approved"
          value={stats?.approved || 0}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
        />
      </div>

      {/* Quick actions */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Quick Actions</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Link
            to="/contents/new"
            className="p-4 border border-primary/30 rounded-lg bg-primary/5 text-center hover:bg-primary/10 focus:outline-none focus:ring-2 focus:ring-primary transition-colors"
          >
            <div className="w-10 h-10 mx-auto text-primary mb-2" aria-hidden="true">
              <svg className="w-10 h-10 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
            </div>
            <p className="font-medium text-gray-900">Create New Content</p>
            <p className="text-xs text-primary mt-1">Start a new draft</p>
          </Link>

          <DisabledAction
            label="My Content"
          >
            <svg className="w-10 h-10 mx-auto text-gray-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
            </svg>
          </DisabledAction>

          <DisabledAction
            label="Import Document"
          >
            <svg className="w-10 h-10 mx-auto text-gray-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
          </DisabledAction>
        </div>
      </div>

      {/* Recent content */}
      <div id="recent-content" className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Recent Content</h2>
          {contents.length > 0 && (
            <span className="text-sm font-medium text-gray-400">{contents.length} total</span>
          )}
        </div>

        {contents.length > 0 ? (
          <div className="divide-y divide-gray-200">
            {recentContents.map(content => (
              <Link
                key={content.id}
                to={`/contents/${content.id}`}
                className="block p-4 hover:bg-gray-50 transition-colors"
              >
                <div className="flex items-center justify-between">
                  <div className="flex-1 min-w-0">
                    <h3 className="font-medium text-gray-900 truncate">{content.title}</h3>
                    <div className="flex items-center gap-3 mt-1 text-sm">
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700">
                        {content.channel}
                      </span>
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium
                        {content.status === 'draft' && 'bg-gray-100 text-gray-700'}
                        {content.status === 'submitted' && 'bg-blue-100 text-blue-700'}
                        {content.status === 'changes_requested' && 'bg-yellow-100 text-yellow-700'}
                        {content.status === 'approved' && 'bg-green-100 text-green-700'}
                      ">
                        {content.status.replace('_', ' ')}
                      </span>
                    </div>
                  </div>
                  <svg className="w-5 h-5 text-gray-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </div>
              </Link>
            ))}
            {contents.length > 5 && (
              <div className="p-4 text-center">
                <span className="text-sm text-gray-500">
                  Showing 5 of {contents.length} content items
                </span>
              </div>
            )}
          </div>
        ) : (
          <EmptyState
            icon={(props) => (
              <svg {...props} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            )}
            title="No content yet"
            description="Create your first draft to get started"
            action={
              <Link
                to="/contents/new"
                className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg font-medium hover:bg-primary-dark focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                Create your first draft
              </Link>
            }
          />
        )}
      </div>

      {/* Guidelines info */}
      <div className="bg-gray-50 rounded-lg p-6">
        <h3 className="font-semibold text-gray-900 mb-2">Active Brand Kit</h3>
        <p className="text-gray-600 text-sm">
          Your content will be reviewed against the active brand kit guidelines.
          Contact your Guideline Owner if you need to know which rules and facts are active.
        </p>
      </div>
    </div>
  );
}

export default CreatorLanding;
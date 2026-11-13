/** Insights landing page - for brand governance insights. */

import React, { useEffect, useState, useRef } from 'react';
import { useAuth } from '../../features/auth/AuthProvider';
import { LoadingScreen } from '../../components/LoadingScreen';
import { GuidelineGapPanel } from './GuidelineGapPanel';
import {
  getContentStatusDistribution,
  getReviewMetrics,
  getFindingInsights,
  type ContentStatusDistribution,
  type ReviewMetrics,
  type FindingInsights,
} from '../../lib/data';

interface StatCardProps {
  label: string;
  value: string | number;
  icon: React.ReactNode;
  href?: string;
  description?: string;
}

function StatCard({ label, value, icon, href, description }: StatCardProps) {
  const content = (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500">{label}</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{value}</p>
          {description && <p className="text-xs text-gray-400 mt-1">{description}</p>}
        </div>
        <div className="p-3 bg-primary-light rounded-lg text-primary">
          {icon}
        </div>
      </div>
    </div>
  );

  return href ? <Link to={href}>{content}</Link> : content;
}

import { Link } from 'react-router-dom';

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="bg-red-50 border border-red-200 rounded-lg p-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-red-800">Unable to load insights</h3>
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

function StatusBadge({ status, count }: { status: string; count: number }) {
  const statusConfig: Record<string, { bg: string; text: string; label: string }> = {
    draft: { bg: 'bg-gray-100', text: 'text-gray-700', label: 'Draft' },
    submitted: { bg: 'bg-blue-100', text: 'text-blue-700', label: 'Submitted' },
    changes_requested: { bg: 'bg-yellow-100', text: 'text-yellow-700', label: 'Changes Requested' },
    approved: { bg: 'bg-green-100', text: 'text-green-700', label: 'Approved' },
  };

  const config = statusConfig[status] || { bg: 'bg-gray-100', text: 'text-gray-700', label: status };

  return (
    <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
      <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${config.bg} ${config.text}`}>
        {config.label}
      </span>
      <span className="text-sm font-medium text-gray-900">{count}</span>
      <div className="flex-1 h-2 bg-gray-200 rounded overflow-hidden">
        <div
          className="h-full bg-primary"
          style={{ width: '100%' }}
        />
      </div>
    </div>
  );
}

function RuleRow({ rule }: { rule: FindingInsights['by_rule'][0] }) {
  const dismissalRatePct = Math.round((rule.dismissal_rate || 0) * 100);

  return (
    <div key={rule.ref_key} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-medium text-gray-900">{rule.ref_key}</span>
          <span className="text-xs text-gray-500 capitalize">{rule.category}</span>
        </div>
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span>{rule.findings} finding{rule.findings !== 1 ? 's' : ''}</span>
          <span>{rule.acted_on} acted on</span>
          <span>{rule.dismissed} dismissed</span>
          <span className={dismissalRatePct >= 50 ? 'text-red-600 font-medium' : ''}>
            {dismissalRatePct}% dismissal rate
          </span>
        </div>
      </div>
    </div>
  );
}

function SeverityRow({ severity, count, total }: { severity: string; count: number; total: number }) {
  const percentage = total > 0 ? Math.round((count / total) * 100) : 0;
  const severityConfig: Record<string, { bg: string; text: string }> = {
    high: { bg: 'bg-red-100', text: 'text-red-700' },
    medium: { bg: 'bg-yellow-100', text: 'text-yellow-700' },
    low: { bg: 'bg-gray-100', text: 'text-gray-700' },
  };

  const config = severityConfig[severity] || { bg: 'bg-gray-100', text: 'text-gray-700' };

  return (
    <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
      <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${config.bg} ${config.text} w-24`}>
        {severity}
      </span>
      <div className="flex-1 h-2 bg-gray-200 rounded overflow-hidden">
        <div
          className="h-full"
          style={{ width: `${percentage}%`, backgroundColor: config.text }}
        />
      </div>
      <span className="text-sm font-medium text-gray-900 w-16 text-right">
        {count} ({percentage}%)
      </span>
    </div>
  );
}

function DismissalReasonRow({ reason, count }: { reason: string; count: number }) {
  return (
    <div className="p-3 bg-gray-50 rounded-lg">
      <p className="text-sm font-medium text-gray-900 truncate" title={reason}>{reason}</p>
      <p className="text-sm text-gray-500 mt-1">{count} occurrence{count !== 1 ? 's' : ''}</p>
    </div>
  );
}

/** Insights dashboard landing page. */
export function InsightsLanding() {
  const { session, isLoading: authLoading } = useAuth();
  const [contentStatus, setContentStatus] = useState<ContentStatusDistribution | null>(null);
  const [reviewMetrics, setReviewMetrics] = useState<ReviewMetrics | null>(null);
  const [findingInsights, setFindingInsights] = useState<FindingInsights | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Request ID for stale-request protection
  const requestIdRef = useRef(0);

  const loadData = async () => {
    const orgId = session?.currentOrgId;
    if (!orgId) {
      setContentStatus(null);
      setReviewMetrics(null);
      setFindingInsights(null);
      setIsLoading(false);
      return;
    }

    const currentRequestId = ++requestIdRef.current;
    setIsLoading(true);
    setError(null);

    try {
      const [statusDist, reviewMets, findingIns] = await Promise.all([
        getContentStatusDistribution(orgId),
        getReviewMetrics(orgId),
        getFindingInsights(orgId),
      ]);

      // Stale request check
      if (currentRequestId !== requestIdRef.current) return;

      setContentStatus(statusDist);
      setReviewMetrics(reviewMets);
      setFindingInsights(findingIns);
    } catch (err) {
      if (currentRequestId !== requestIdRef.current) return;
      setError(err instanceof Error ? err.message : 'Failed to load insights data');
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
    return <LoadingScreen message="Loading insights data..." />;
  }

  if (error) {
    return (
      <div className="space-y-8">
        <ErrorState message={error} onRetry={loadData} />
      </div>
    );
  }

  const hasData = contentStatus && contentStatus.total > 0;

  return (
    <div className="space-y-8">
      {/* Welcome header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          Insights
        </h1>
        <p className="text-gray-600 mt-1">
          Understand review progress, brand rule effectiveness, and governance patterns.
        </p>
      </div>

      <GuidelineGapPanel />

      {/* Overview cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          label="Total Content"
          value={contentStatus?.total || 0}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          }
          description={hasData ? 'All content items in this organization' : 'No content yet'}
        />
        <StatCard
          label="Total Reviews"
          value={reviewMetrics?.total_reviews || 0}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
            </svg>
          }
          description={reviewMetrics && reviewMetrics.total_reviews > 0
            ? `${reviewMetrics.done} completed, ${reviewMetrics.llm_failed} with LLM issues`
            : 'No reviews yet'}
        />
        <StatCard
          label="Total Findings"
          value={findingInsights?.total_findings || 0}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          }
          description={findingInsights && findingInsights.total_findings > 0
            ? `${findingInsights.accepted} accepted, ${findingInsights.dismissed} dismissed, ${findingInsights.pending_decision} pending`
            : 'No findings yet'}
        />
        <StatCard
          label="Validator Drop Rate"
          value={reviewMetrics && reviewMetrics.total_llm_findings_raw > 0
            ? `${Math.round(reviewMetrics.validator_drop_rate * 100)}%`
            : 'N/A'}
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
          description={reviewMetrics && reviewMetrics.total_llm_findings_raw > 0
            ? `${reviewMetrics.total_llm_findings_dropped} of ${reviewMetrics.total_llm_findings_raw} LLM findings dropped`
            : 'No LLM findings to validate'}
        />
      </div>

      {/* Content Status Distribution */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Content Status Distribution</h2>
        {contentStatus && contentStatus.total > 0 ? (
          <div className="space-y-3">
            <StatusBadge status="draft" count={contentStatus.draft} />
            <StatusBadge status="submitted" count={contentStatus.submitted} />
            <StatusBadge status="changes_requested" count={contentStatus.changes_requested} />
            <StatusBadge status="approved" count={contentStatus.approved} />
          </div>
        ) : (
          <EmptyState
            icon={(props) => (
              <svg {...props} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            )}
            title="No content yet"
            description="Content status distribution will appear once content is created"
          />
        )}
      </div>

      {/* Findings by Rule */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Findings by Brand Rule</h2>
        {findingInsights && findingInsights.by_rule.length > 0 ? (
          <div className="space-y-3">
            {findingInsights.by_rule.map((rule) => (
              <RuleRow key={rule.ref_key} rule={rule} />
            ))}
          </div>
        ) : (
          <EmptyState
            icon={(props) => (
              <svg {...props} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
              </svg>
            )}
            title="No rule statistics yet"
            description="Rule-level insights will appear once reviews generate findings"
          />
        )}
      </div>

      {/* Decision Outcomes */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Decision Outcomes</h2>
          {findingInsights && findingInsights.total_findings > 0 ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between p-3 bg-green-50 rounded-lg">
                <span className="font-medium text-gray-900">Accepted</span>
                <span className="text-2xl font-bold text-green-700">{findingInsights.accepted}</span>
              </div>
              <div className="flex items-center justify-between p-3 bg-blue-50 rounded-lg">
                <span className="font-medium text-gray-900">Edited</span>
                <span className="text-2xl font-bold text-blue-700">{findingInsights.edited}</span>
              </div>
              <div className="flex items-center justify-between p-3 bg-red-50 rounded-lg">
                <span className="font-medium text-gray-900">Dismissed</span>
                <span className="text-2xl font-bold text-red-700">{findingInsights.dismissed}</span>
              </div>
              <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <span className="font-medium text-gray-900">Pending Decision</span>
                <span className="text-2xl font-bold text-gray-700">{findingInsights.pending_decision}</span>
              </div>
              <div className="flex items-center justify-between p-3 bg-primary-light rounded-lg">
                <span className="font-medium text-gray-900">Total Findings</span>
                <span className="text-2xl font-bold text-primary">{findingInsights.total_findings}</span>
              </div>
            </div>
          ) : (
            <EmptyState
              icon={(props) => (
                <svg {...props} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              )}
              title="No decisions yet"
              description="Decision outcomes will appear once findings are reviewed"
            />
          )}
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Findings by Severity</h2>
          {findingInsights && findingInsights.total_findings > 0 ? (
            <div className="space-y-3">
              {(['high', 'medium', 'low'] as const).map((severity) => (
                <SeverityRow
                  key={severity}
                  severity={severity}
                  count={findingInsights.by_severity[severity] || 0}
                  total={findingInsights.total_findings}
                />
              ))}
            </div>
          ) : (
            <EmptyState
              icon={(props) => (
                <svg {...props} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              )}
              title="No severity data"
              description="Severity distribution will appear once findings exist"
            />
          )}
        </div>
      </div>

      {/* Dismissal Reasons */}
      {findingInsights && findingInsights.dismissal_reasons.length > 0 && (
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Dismissal Reasons</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {findingInsights.dismissal_reasons.map(({ reason, count }, idx) => (
              <DismissalReasonRow key={idx} reason={reason} count={count} />
            ))}
          </div>
        </div>
      )}

      {/* Findings by Category */}
      {findingInsights && Object.keys(findingInsights.by_category).length > 0 && (
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Findings by Category</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {Object.entries(findingInsights.by_category).map(([category, count]) => (
              <div key={category} className="p-3 bg-gray-50 rounded-lg">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{category}</p>
                <p className="text-2xl font-bold text-gray-900">{count}</p>
                <p className="text-xs text-gray-400">
                  {findingInsights.total_findings > 0
                    ? `${Math.round((count / findingInsights.total_findings) * 100)}% of findings`
                    : ''}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Review Health */}
      {reviewMetrics && reviewMetrics.total_reviews > 0 && (
        <div className="bg-gray-50 rounded-lg p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Review Engine Health</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 bg-white rounded-lg">
              <p className="text-sm font-medium text-gray-500">Completed Reviews</p>
              <p className="text-2xl font-bold text-gray-900">{reviewMetrics.done}</p>
              <p className="text-xs text-gray-400">
                {reviewMetrics.total_reviews > 0
                  ? `${Math.round((reviewMetrics.done / reviewMetrics.total_reviews) * 100)}% of total`
                  : ''}
              </p>
            </div>
            <div className="p-4 bg-white rounded-lg">
              <p className="text-sm font-medium text-gray-500">LLM Success Rate</p>
              <p className="text-2xl font-bold text-gray-900">
                {reviewMetrics.llm_ok + reviewMetrics.llm_skipped > 0
                  ? `${Math.round(((reviewMetrics.llm_ok + reviewMetrics.llm_skipped) / (reviewMetrics.llm_ok + reviewMetrics.llm_skipped + reviewMetrics.llm_failed)) * 100)}%`
                  : 'N/A'}
              </p>
              <p className="text-xs text-gray-400">
                {reviewMetrics.llm_ok} ok, {reviewMetrics.llm_skipped} skipped, {reviewMetrics.llm_failed} failed
              </p>
            </div>
            <div className="p-4 bg-white rounded-lg">
              <p className="text-sm font-medium text-gray-500">Validator Drop Rate</p>
              <p className="text-2xl font-bold text-gray-900">
                {reviewMetrics.total_llm_findings_raw > 0
                  ? `${Math.round(reviewMetrics.validator_drop_rate * 10000) / 100}%`
                  : 'N/A'}
              </p>
              <p className="text-xs text-gray-400">
                {reviewMetrics.total_llm_findings_dropped} of {reviewMetrics.total_llm_findings_raw} dropped
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Guidelines */}
      <div className="bg-gray-50 rounded-lg p-6">
        <h3 className="font-semibold text-gray-900 mb-2">Insights Guidelines</h3>
        <ul className="text-gray-600 text-sm space-y-1">
          <li>• Content counts unique content records, not revisions.</li>
          <li>• Review metrics reflect all review records for this organization.</li>
          <li>• Finding counts include all findings across all revisions and reviews.</li>
          <li>• Decisions use the latest decision per finding (persisted in database).</li>
          <li>• Rule statistics use stable rule keys (e.g., TERM-01) so insights work across kit versions.</li>
          <li>• Dismissal reasons show only when a reason was provided at dismissal.</li>
        </ul>
      </div>
    </div>
  );
}

export default InsightsLanding;
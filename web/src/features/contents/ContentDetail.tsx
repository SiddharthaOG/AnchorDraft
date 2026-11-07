/** Content detail page - shows content, revisions, review status, findings, and allows decisions/revisions. */

import { useEffect, useState, useRef, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../features/auth/AuthProvider';
import { LoadingScreen } from '../../components/LoadingScreen';
import {
  getContents,
  getLatestRevision,
  getRevisions,
  getLatestReviewForRevision,
  getFindingsWithDecisionsForReview,
  getPendingSignoffs,
  createRevision,
  submitContent,
  recordDecision,
  applyDecisions,
  type Content,
  type Revision,
  type Review,
  type FindingWithDecision,
} from '../../lib/data';
import { startReview } from '../../lib/data';

interface FindingDisplay extends FindingWithDecision {
  displayQuote: string;
}

function StatusBadge({ status }: { status: Content['status'] }) {
  const colors = {
    draft: 'bg-gray-100 text-gray-800',
    submitted: 'bg-blue-100 text-blue-800',
    changes_requested: 'bg-yellow-100 text-yellow-800',
    approved: 'bg-green-100 text-green-800',
  };
  const labels = {
    draft: 'Draft',
    submitted: 'Submitted',
    changes_requested: 'Changes Requested',
    approved: 'Approved',
  };
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${colors[status]}`}>
      {labels[status]}
    </span>
  );
}

function ReviewStatusBadge({ status, llm_status }: { status: Review['status']; llm_status: Review['llm_status'] }) {
  if (status === 'failed') {
    return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">Failed</span>;
  }
  if (status === 'running') {
    return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 animate-pulse">Running</span>;
  }
  if (status === 'queued') {
    return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">Queued</span>;
  }
  if (llm_status === 'failed') {
    return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-800">Done (LLM Failed)</span>;
  }
  if (llm_status === 'skipped') {
    return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">Done (Deterministic Only)</span>;
  }
  return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">Done</span>;
}

function SeverityBadge({ severity }: { severity: FindingWithDecision['severity'] }) {
  const colors = {
    high: 'bg-red-100 text-red-800',
    medium: 'bg-yellow-100 text-yellow-800',
    low: 'bg-green-100 text-green-800',
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${colors[severity]}`}>
      {severity.charAt(0).toUpperCase() + severity.slice(1)}
    </span>
  );
}

function SourceBadge({ source }: { source: FindingWithDecision['source'] }) {
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700">
      {source === 'deterministic' ? 'Deterministic' : 'LLM'}
    </span>
  );
}

function ErrorAlert({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  return (
    <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center justify-between">
      <p className="text-red-700 text-sm">{message}</p>
      <button onClick={onDismiss} className="text-red-500 hover:text-red-700 font-bold text-lg leading-none p-1">
        ×
      </button>
    </div>
  );
}

function ConfirmDialog({ isOpen, title, message, onConfirm, onCancel, confirmText, variant = 'danger' }: {
  isOpen: boolean;
  title: string;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
  confirmText: string;
  variant?: 'danger' | 'primary';
}) {
  if (!isOpen) return null;

  const confirmColors = variant === 'danger'
    ? 'bg-red-600 hover:bg-red-700'
    : 'bg-primary hover:bg-primary-dark';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-2">{title}</h3>
        <p className="text-gray-600 mb-6">{message}</p>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className={`px-4 py-2 text-sm font-medium text-white rounded-lg ${confirmColors}`}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}

function FindingCard({
  finding,
  onAccept,
  onDismiss,
  isContentEditable,
  hasDecision,
}: {
  finding: FindingDisplay;
  onAccept: () => void;
  onDismiss: () => void;
  isContentEditable: boolean;
  hasDecision: boolean;
}) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <SeverityBadge severity={finding.severity} />
            <SourceBadge source={finding.source} />
            {finding.needs_reviewer && (
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-700">
                Needs Reviewer
              </span>
            )}
            {finding.needs_human && (
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-700">
                Needs Human Review
              </span>
            )}
            <code className="px-2 py-0.5 bg-gray-100 rounded text-xs font-mono text-gray-700">{finding.ref_key}</code>
          </div>

          <p className="font-medium text-gray-900 mb-2">
            {finding.category.charAt(0).toUpperCase() + finding.category.slice(1)} Issue
          </p>

          <div className="bg-gray-50 rounded-lg p-3 mb-3">
            <p className="text-sm text-gray-700 italic">"{finding.quote}"</p>
          </div>

          <p className="text-sm text-gray-600 mb-3">{finding.explanation}</p>

          {finding.suggestion && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-3">
              <p className="text-xs font-medium text-blue-800 mb-1">Suggestion</p>
              <p className="text-sm text-blue-700">{finding.suggestion}</p>
            </div>
          )}

          {finding.last_action && (
            <div className="text-xs text-gray-500 mb-2">
              Last action: <span className="font-medium capitalize">{finding.last_action}</span>
              {finding.last_reason && <span className="ml-1">- {finding.last_reason}</span>}
            </div>
          )}
        </div>

        {isContentEditable && !hasDecision && (
          <div className="flex items-center gap-2 flex-shrink-0">
            {finding.suggestion && (
              <button
                onClick={onAccept}
                className="px-3 py-1.5 text-sm font-medium text-white bg-green-600 rounded-lg hover:bg-green-700"
              >
                Accept
              </button>
            )}
            <button
              onClick={onDismiss}
              className="px-3 py-1.5 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50"
            >
              Dismiss
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/** Renders the review status section to avoid complex ternary nesting in JSX. */
function ReviewStatusSection({
  latestReview,
  findings,
  startingReview,
  handleStartReview,
  isContentEditable,
}: {
  latestReview: Review | null;
  findings: FindingDisplay[];
  startingReview: boolean;
  handleStartReview: () => void;
  isContentEditable: boolean;
}) {
  if (!latestReview) {
    return (
      <div className="text-center py-8 text-gray-500">
        <p>No review started for this revision.</p>
        {isContentEditable && (
          <button
            onClick={handleStartReview}
            disabled={startingReview}
            className="mt-4 px-4 py-2 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary-dark disabled:opacity-50"
          >
            {startingReview ? 'Starting...' : 'Start Review'}
          </button>
        )}
      </div>
    );
  }

  const renderRunning = () => (
    <div className="space-y-2">
      <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
        <div className="h-full bg-primary animate-pulse" style={{ width: latestReview.status === 'running' ? '50%' : '20%' }} />
      </div>
      <p className="text-sm text-gray-500">
        {latestReview.status === 'running' ? 'Review is in progress...' : 'Review queued...'}
      </p>
    </div>
  );

  const renderFailed = () => (
    <div className="bg-red-50 border border-red-200 rounded-lg p-4">
      <p className="font-medium text-red-800">Review Failed</p>
      <p className="text-red-600 text-sm mt-1">{latestReview.error || 'Unknown error'}</p>
      <button
        onClick={handleStartReview}
        disabled={startingReview}
        className="mt-3 px-4 py-2 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary-dark disabled:opacity-50"
      >
        {startingReview ? 'Retrying...' : 'Retry Review'}
      </button>
    </div>
  );

  const renderDone = () => (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="font-medium text-gray-900">Findings</p>
        <span className="text-sm text-gray-500">{findings.length} finding{findings.length !== 1 ? 's' : ''}</span>
      </div>

      {latestReview.llm_status === 'failed' && (
        <p className="text-sm text-orange-600 bg-orange-50 border border-orange-200 rounded-lg p-2">
          LLM processing failed. Only deterministic findings are shown.
        </p>
      )}
    </div>
  );

  const statusContent = (() => {
    switch (latestReview.status) {
      case 'running':
      case 'queued':
        return renderRunning();
      case 'failed':
        return renderFailed();
      case 'done':
        return renderDone();
      default:
        return null;
    }
  })();

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <ReviewStatusBadge status={latestReview.status} llm_status={latestReview.llm_status} />
        <div className="text-sm text-gray-600">
          Kit {latestReview.kit_id} • {latestReview.status}
          {latestReview.llm_status !== 'ok' && <span className="ml-2 text-orange-600">(LLM: {latestReview.llm_status})</span>}
        </div>
      </div>
      {statusContent}
    </div>
  );
}

/** Content detail page with review workflow. */
export function ContentDetail() {
  const { session, isLoading: authLoading } = useAuth();
  const { contentId } = useParams<{ contentId: string }>();
  const navigate = useNavigate();

  const [content, setContent] = useState<Content | null>(null);
  const [latestRevision, setLatestRevision] = useState<Revision | null>(null);
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [latestReview, setLatestReview] = useState<Review | null>(null);
  const [findings, setFindings] = useState<FindingDisplay[]>([]);
  const [pendingSignoffs, setPendingSignoffs] = useState<number>(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Action states
  const [submitting, setSubmitting] = useState(false);
  const [isCreatingRevision, setIsCreatingRevision] = useState(false);
  const [startingReview, setStartingReview] = useState(false);
  const [applyingDecisions, setApplyingDecisions] = useState(false);

  // Editor visibility state (separate from mutation state)
  const [isRevisionEditorOpen, setIsRevisionEditorOpen] = useState(false);

  // Single-submission guards
  const submittingRef = useRef(false);
  const creatingRevisionRef = useRef(false);
  const startingReviewRef = useRef(false);
  const applyingDecisionsRef = useRef(false);

  // Error states
  const [toastError, setToastError] = useState<string | null>(null);

  // Dismiss confirmation
  const [dismissConfirm, setDismissConfirm] = useState<{ findingId: string; findingKey: string } | null>(null);

  // Stale request protection
  const requestIdRef = useRef(0);

  // Polling for review status
  const pollTimerRef = useRef<number | null>(null);
  const revisionIdRef = useRef<string | null>(null);
  const reviewRequestIdRef = useRef(0);
  const pollGenerationRef = useRef(0);
  const pollInFlightRef = useRef<number | null>(null);

  // Textarea ref for reliable value reading
  const revisionTextareaRef = useRef<HTMLTextAreaElement>(null);

  const loadContent = useCallback(async () => {
    if (!contentId || !session?.currentOrgId) return;

    const currentRequestId = ++requestIdRef.current;
    setIsLoading(true);
    setError(null);

    try {
      const allContents = await getContents(session.currentOrgId);
      const foundContent = allContents.find(c => c.id === contentId);

      if (!foundContent) {
        throw new Error('Content not found');
      }

      if (currentRequestId !== requestIdRef.current) return;

      setContent(foundContent);

      const [rev, revs] = await Promise.all([
        getLatestRevision(contentId),
        getRevisions(contentId),
      ]);

      if (currentRequestId !== requestIdRef.current) return;

      // Invalidate all outstanding review-data requests for the previous revision.
      reviewRequestIdRef.current += 1;
      revisionIdRef.current = rev?.id ?? null;

      // Stop any polling associated with the previous revision.
      if (pollTimerRef.current !== null) {
        window.clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }


      setLatestReview(null);
      setFindings([]);
      setPendingSignoffs(0);

      setLatestRevision(rev);
      setRevisions(revs);
    } catch (err) {
      if (currentRequestId !== requestIdRef.current) return;
      setError(err instanceof Error ? err.message : 'Failed to load content');
    } finally {
      if (currentRequestId === requestIdRef.current) {
        setIsLoading(false);
      }
    }
  }, [contentId, session?.currentOrgId]);

  const loadReviewData = useCallback(async () => {
    const revisionId = latestRevision?.id;

    if (!revisionId || pollTimerRef.current !== null) return;


    const requestId = ++reviewRequestIdRef.current;

    try {
      const review = await getLatestReviewForRevision(revisionId);

      // Do not apply results if another request or revision superseded this one.
      if (
        requestId !== reviewRequestIdRef.current ||
        revisionId !== revisionIdRef.current
      ) {
        return;
      }

      setLatestReview(review);

      if (!review) {
        setFindings([]);
        setPendingSignoffs(0);
        return;
      }

      const [findingsData, signoffs] = await Promise.all([
        getFindingsWithDecisionsForReview(review.id),
        getPendingSignoffs(contentId!),
      ]);

      // Check again after the asynchronous data fetches.
      if (
        requestId !== reviewRequestIdRef.current ||
        revisionId !== revisionIdRef.current
      ) {
        return;
      }

      setFindings(findingsData as FindingDisplay[]);
      setPendingSignoffs(signoffs.length);
    } catch (err) {
      if (
        requestId !== reviewRequestIdRef.current ||
        revisionId !== revisionIdRef.current
      ) {
        return;
      }

      console.error('Failed to load review data:', err);
      setFindings([]);
      setPendingSignoffs(0);
      setToastError(
        err instanceof Error ? err.message : 'Failed to load review data'
      );
    }
  }, [latestRevision?.id, contentId]);


  // Polling for review status when review is queued or running

const stopPolling = useCallback(() => {
  // Invalidate every poll belonging to the previous generation.
  pollGenerationRef.current += 1;

  if (pollTimerRef.current !== null) {
    window.clearInterval(pollTimerRef.current);
    pollTimerRef.current = null;
  }
}, []);

const startPolling = useCallback(() => {
  const revisionId = latestRevision?.id;

  if (!revisionId || pollTimerRef.current !== null) return;

  // Assign a unique generation to this polling session.
  const generation = ++pollGenerationRef.current;

  const poll = async () => {
    // Ignore polls belonging to an outdated generation.
    if (generation !== pollGenerationRef.current) return;

    // Prevent overlapping requests within this generation.
    if (pollInFlightRef.current === generation) return;

    // Stop if the active revision has changed.
    if (revisionIdRef.current !== revisionId) {
      stopPolling();
      return;
    }

    pollInFlightRef.current = generation;

    try {
      const review = await getLatestReviewForRevision(revisionId);

      // Ignore stale responses.
      if (
        generation !== pollGenerationRef.current ||
        revisionIdRef.current !== revisionId
      ) {
        return;
      }

      if (!review) {
        stopPolling();
        return;
      }

      setLatestReview(review);

      if (review.status === 'done' || review.status === 'failed') {
        const [findingsData, signoffs] = await Promise.all([
          getFindingsWithDecisionsForReview(review.id),
          getPendingSignoffs(contentId!),
        ]);

        // Recheck after asynchronous requests finish.
        if (
          generation !== pollGenerationRef.current ||
          revisionIdRef.current !== revisionId
        ) {
          return;
        }

        setFindings(findingsData as FindingDisplay[]);
        setPendingSignoffs(signoffs.length);

        stopPolling();
      }
    } catch (err) {
      if (
        generation === pollGenerationRef.current &&
        revisionIdRef.current === revisionId
      ) {
        console.error('Polling failed:', err);
        setToastError(
          err instanceof Error ? err.message : 'Review status polling failed'
        );
        stopPolling();
      }
    } finally {
      // An old poll must never clear a newer generation's lock.
      if (pollInFlightRef.current === generation) {
        pollInFlightRef.current = null;
      }
    }
  };

  // Poll immediately, then every three seconds.
  void poll();

  pollTimerRef.current = window.setInterval(() => {
    void poll();
  }, 3000);
}, [latestRevision?.id, contentId, stopPolling]);


  // Start/stop polling when review status changes
  useEffect(() => {
    if (latestReview && (latestReview.status === 'queued' || latestReview.status === 'running')) {
      startPolling();
    } else {
      stopPolling();
    }

    return () => stopPolling();
  }, [latestReview, startPolling, stopPolling]);

  // Cleanup on unmount: invalidate pending review requests and stop polling
  useEffect(() => {
    return () => {
      reviewRequestIdRef.current += 1;
      stopPolling();
    };
  }, [stopPolling]);

  useEffect(() => {
    if (!authLoading && session && contentId) {
      loadContent();
    }
  }, [authLoading, session, contentId, loadContent]);

  useEffect(() => {
    loadReviewData();
  }, [loadReviewData]);

  // Invalidate review data when content changes
  useEffect(() => {
    setLatestReview(null);
    setFindings([]);
    setPendingSignoffs(0);
  }, [contentId]);

  const handleSubmit = async () => {
    if (!content || !latestRevision) return;
    if (submittingRef.current) return;

    submittingRef.current = true;
    setSubmitting(true);
    setToastError(null);

    try {
      await submitContent(content.id);
      // Reload content to get updated status
      await loadContent();
    } catch (err) {
      setToastError(err instanceof Error ? err.message : 'Failed to submit content');
    } finally {
      setSubmitting(false);
      submittingRef.current = false;
    }
  };

  // Shared handler for Create Revision (button and Ctrl+Enter)
  const handleCreateRevisionSubmit = useCallback(async () => {
    if (!content) return;
    if (creatingRevisionRef.current) return;

    const body = revisionTextareaRef.current?.value ?? '';
    // Validate: not empty or whitespace-only
    if (!body.trim()) {
      setToastError('Revision content cannot be empty');
      return;
    }

    creatingRevisionRef.current = true;
    setIsCreatingRevision(true);
    setToastError(null);

    try {
      await createRevision(content.id, body);
      // On success: close editor, clear ref, reload content/revisions
      setIsRevisionEditorOpen(false);
      revisionTextareaRef.current = null; // Clear ref after success
      await loadContent();
    } catch (err) {
      // On failure: preserve editor and entered text, show error
      setToastError(err instanceof Error ? err.message : 'Failed to create revision');
    } finally {
      setIsCreatingRevision(false);
      creatingRevisionRef.current = false;
    }
  }, [content, loadContent]);

  const handleStartReview = async () => {
    if (!latestRevision) return;
    if (startingReviewRef.current) return;

    startingReviewRef.current = true;
    setStartingReview(true);
    setToastError(null);

    try {
      const result = await startReview(latestRevision.id);
      // Reload review data to show new review
      await loadReviewData();
      return result;
    } catch (err) {
      if (err instanceof Error && 'status' in err && (err as any).status === 409) {
        setToastError(`Cannot start review: ${err.message}`);
      } else {
        setToastError(err instanceof Error ? err.message : 'Failed to start review');
      }
    } finally {
      setStartingReview(false);
      startingReviewRef.current = false;
    }
  };

  const handleAcceptFinding = async (findingId: string) => {
    try {
      await recordDecision(findingId, 'accept');
      await loadReviewData();
    } catch (err) {
      setToastError(err instanceof Error ? err.message : 'Failed to record decision');
    }
  };

  const handleDismissFinding = async (findingId: string, reason: string) => {
    try {
      await recordDecision(findingId, 'dismiss', reason);
      await loadReviewData();
    } catch (err) {
      setToastError(err instanceof Error ? err.message : 'Failed to record decision');
    }
  };

  const handleApplyDecisions = async () => {
    if (!content) return;
    if (applyingDecisionsRef.current) return;

    applyingDecisionsRef.current = true;
    setApplyingDecisions(true);
    setToastError(null);

    try {
      await applyDecisions(content.id);
      // Reload content to get new revision
      await loadContent();
      // Start new review automatically
      const newLatestRevision = await getLatestRevision(content.id);
      if (newLatestRevision) {
        await startReview(newLatestRevision.id);
      }
    } catch (err) {
      setToastError(err instanceof Error ? err.message : 'Failed to apply decisions');
    } finally {
      setApplyingDecisions(false);
      applyingDecisionsRef.current = false;
    }
  };

  const confirmDismiss = (finding: FindingDisplay) => {
    setDismissConfirm({ findingId: finding.id, findingKey: finding.ref_key });
  };

  const executeDismiss = (reason: string) => {
    if (dismissConfirm) {
      handleDismissFinding(dismissConfirm.findingId, reason);
      setDismissConfirm(null);
    }
  };

  // Open editor handler
  const handleOpenRevisionEditor = () => {
    setIsRevisionEditorOpen(true);
    // Focus textarea after render
    setTimeout(() => {
      revisionTextareaRef.current?.focus();
    }, 0);
  };

  // Close editor handler (cancel)
  const handleCloseRevisionEditor = () => {
    setIsRevisionEditorOpen(false);
    revisionTextareaRef.current = null;
  };

  if (authLoading || !session) {
    return <LoadingScreen message="Loading authentication..." />;
  }

  if (isLoading) {
    return <LoadingScreen message="Loading content..." />;
  }

  if (error || !content) {
    return (
      <div className="space-y-8">
        <Link to="/" className="text-primary hover:text-primary-dark inline-flex items-center gap-1">
          ← Back to Dashboard
        </Link>
        <ErrorAlert message={error || 'Content not found'} onDismiss={() => navigate('/')} />
      </div>
    );
  }

  const isContentEditable = content.status === 'draft' || content.status === 'changes_requested';
  const hasLatestReview = !!latestReview;
  const hasPendingDecisions = findings.some(f => (f.last_action === 'accept' || f.last_action === 'edit') && !f.resulting_revision_id);
  const hasDecisions = findings.some(f => f.last_action);
  // Zero findings is valid - all findings (zero) are decided vacuously
  const allFindingsDecided = findings.every(f => f.last_action);
  const canSubmit = isContentEditable && hasLatestReview && latestReview?.status === 'done' &&
    (latestReview.llm_status === 'ok' || latestReview.llm_status === 'skipped') &&
    allFindingsDecided && !hasPendingDecisions;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-4">
          <Link to="/" className="text-primary hover:text-primary-dark inline-flex items-center gap-1">
            ← Back
          </Link>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-gray-900">{content.title}</h1>
              <StatusBadge status={content.status} />
            </div>
            <p className="text-sm text-gray-500 mt-1">
              Channel: {content.channel} • Created {new Date(content.created_at).toLocaleDateString()}
              {content.updated_at && ` • Updated ${new Date(content.updated_at).toLocaleDateString()}`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {isContentEditable && (
            <button
              onClick={handleOpenRevisionEditor}
              disabled={isCreatingRevision}
              className="px-4 py-2 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary-dark disabled:opacity-50"
            >
              {isCreatingRevision ? 'Creating...' : 'New Revision'}
            </button>
          )}
          {canSubmit && (
            <button
              onClick={handleSubmit}
              disabled={submitting}
              className="px-4 py-2 text-sm font-medium text-white bg-green-600 rounded-lg hover:bg-green-700 disabled:opacity-50"
            >
              {submitting ? 'Submitting...' : 'Submit for Review'}
            </button>
          )}
        </div>
      </div>

      {/* Error toast */}
      {toastError && (
        <ErrorAlert message={toastError} onDismiss={() => setToastError(null)} />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Main content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Revision selector */}
          <div className="bg-white border border-gray-200 rounded-lg">
            <div className="p-4 border-b border-gray-200">
              <h2 className="font-semibold text-gray-900">Revisions</h2>
            </div>
            <div className="divide-y divide-gray-200">
              {revisions.map(rev => (
                <button
                  key={rev.id}
                  onClick={() => {
                    // For now, just show latest. Could add revision switching later.
                  }}
                  className={`w-full px-4 py-3 text-left hover:bg-gray-50 transition-colors ${rev.id === latestRevision?.id ? 'bg-blue-50' : ''}`}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="font-medium text-gray-900">Revision {rev.version}</span>
                      <span className="ml-2 text-xs text-gray-500">{new Date(rev.created_at).toLocaleString()}</span>
                    </div>
                    {rev.id === latestRevision?.id && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">
                        Current
                      </span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Content body */}
          <div className="bg-white border border-gray-200 rounded-lg">
            <div className="p-4 border-b border-gray-200">
              <h2 className="font-semibold text-gray-900">Content</h2>
            </div>
            <div className="p-6">
              <pre className="whitespace-pre-wrap font-mono text-sm text-gray-800 bg-gray-50 p-4 rounded-lg max-h-96 overflow-y-auto">
                {latestRevision?.body || 'No content'}
              </pre>
            </div>
          </div>

          {/* Review Status */}
          <div className="bg-white border border-gray-200 rounded-lg">
            <div className="p-4 border-b border-gray-200 flex items-center justify-between">
              <h2 className="font-semibold text-gray-900">Review Status</h2>
              {hasLatestReview && latestReview && latestReview.status !== 'done' && latestReview.status !== 'failed' && (
                <span className="text-xs text-gray-500">Auto-refreshes when complete</span>
              )}
            </div>
            <div className="p-4">
              <ReviewStatusSection
                latestReview={latestReview}
                findings={findings}
                startingReview={startingReview}
                handleStartReview={handleStartReview}
                isContentEditable={isContentEditable}
              />
            </div>
          </div>

          {/* Findings */}
          {hasLatestReview && latestReview?.status === 'done' && findings.length > 0 && (
            <div className="bg-white border border-gray-200 rounded-lg">
              <div className="p-4 border-b border-gray-200">
                <h2 className="font-semibold text-gray-900">Findings ({findings.length})</h2>
              </div>
              <div className="divide-y divide-gray-200">
                {findings.map(finding => (
                  <FindingCard
                    key={finding.id}
                    finding={finding}
                    onAccept={() => handleAcceptFinding(finding.id)}
                    onDismiss={() => confirmDismiss(finding)}
                    isContentEditable={isContentEditable}
                    hasDecision={!!finding.last_action}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Decisions & Actions */}
          {(hasLatestReview && latestReview?.status === 'done' && isContentEditable) && (
            <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-4">
              <h2 className="font-semibold text-gray-900">Actions</h2>

              {hasPendingDecisions && (
                <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                  <p className="font-medium text-yellow-800 mb-2">Pending Decisions</p>
                  <p className="text-sm text-yellow-700 mb-3">
                    You have {findings.filter(f => (f.last_action === 'accept' || f.last_action === 'edit') && !f.resulting_revision_id).length} accepted/edited finding{findings.filter(f => (f.last_action === 'accept' || f.last_action === 'edit') && !f.resulting_revision_id).length !== 1 ? 's' : ''} waiting to be applied.
                  </p>
                  <button
                    onClick={handleApplyDecisions}
                    disabled={applyingDecisions}
                    className="px-4 py-2 text-sm font-medium text-white bg-yellow-600 rounded-lg hover:bg-yellow-700 disabled:opacity-50"
                  >
                    {applyingDecisions ? 'Applying...' : 'Apply Decisions'}
                  </button>
                </div>
              )}

              {!hasPendingDecisions && allFindingsDecided && canSubmit && (
                <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                  <p className="font-medium text-green-800 mb-2">Ready to Submit</p>
                  <p className="text-sm text-green-700 mb-3">
                    {findings.length === 0
                      ? 'No findings were generated. You can submit this content for approval.'
                      : 'All findings have been decided. You can submit this content for approval.'}
                  </p>
                  <button
                    onClick={handleSubmit}
                    disabled={submitting}
                    className="px-4 py-2 text-sm font-medium text-white bg-green-600 rounded-lg hover:bg-green-700 disabled:opacity-50"
                  >
                    {submitting ? 'Submitting...' : 'Submit for Review'}
                  </button>
                </div>
              )}

              {!hasDecisions && allFindingsDecided && findings.length > 0 && canSubmit && (
                <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                  <p className="font-medium text-gray-800 mb-2">No Findings Decided</p>
                  <p className="text-sm text-gray-600 mb-3">
                    You need to accept or dismiss all findings before submitting.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* New Revision Form */}
          {isRevisionEditorOpen && (
            <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-gray-900">Create New Revision</h3>
                <button
                  onClick={handleCloseRevisionEditor}
                  disabled={isCreatingRevision}
                  className="text-gray-400 hover:text-gray-600 text-xl leading-none p-1 disabled:opacity-50"
                >
                  ×
                </button>
              </div>
              <textarea
                ref={revisionTextareaRef}
                defaultValue={latestRevision?.body || ''}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                    e.preventDefault();
                    handleCreateRevisionSubmit();
                  }
                }}
                rows={15}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent font-mono text-sm"
                placeholder="Edit content for new revision..."
              />
              <div className="flex justify-end gap-3">
                <button
                  onClick={handleCloseRevisionEditor}
                  disabled={isCreatingRevision}
                  className="px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreateRevisionSubmit}
                  disabled={isCreatingRevision}
                  className="px-4 py-2 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary-dark disabled:opacity-50"
                >
                  {isCreatingRevision ? 'Creating...' : 'Create Revision'}
                </button>
              </div>
            </div>
          )}

          {/* Dismiss Confirmation Dialog */}
          <ConfirmDialog
            isOpen={!!dismissConfirm}
            title="Dismiss Finding"
            message={`Are you sure you want to dismiss finding "${dismissConfirm?.findingKey}"? You must provide a reason.`}
            onConfirm={() => {
              const reason = prompt('Reason for dismissal (required):');
              if (reason && reason.trim()) {
                executeDismiss(reason.trim());
              } else if (reason !== null) {
                alert('Dismissal requires a reason.');
              }
            }}
            onCancel={() => setDismissConfirm(null)}
            confirmText="Dismiss"
            variant="danger"
          />
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Content Info */}
          <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-4">
            <h3 className="font-semibold text-gray-900">Content Info</h3>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-gray-500">Status</dt>
                <dd className="font-medium">{content.status.replace('_', ' ')}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Channel</dt>
                <dd className="font-medium capitalize">{content.channel}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Purpose</dt>
                <dd className="font-medium truncate max-w-[200px]">{content.purpose}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Created</dt>
                <dd className="font-medium">{new Date(content.created_at).toLocaleDateString()}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Updated</dt>
                <dd className="font-medium">{content.updated_at ? new Date(content.updated_at).toLocaleDateString() : '—'}</dd>
              </div>
            </dl>
          </div>

          {/* Review Actions */}
          {hasLatestReview && latestReview && latestReview.status === 'done' && latestReview.llm_status === 'failed' && (
            <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-4">
              <h3 className="font-semibold text-gray-900">LLM Processing Failed</h3>
              <p className="text-sm text-gray-600">
                The LLM processing failed. Only deterministic findings are shown. You can retry the review.
              </p>
              <button
                onClick={handleStartReview}
                disabled={startingReview}
                className="w-full px-4 py-2 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary-dark disabled:opacity-50"
              >
                {startingReview ? 'Retrying...' : 'Retry Review'}
              </button>
            </div>
          )}

          {/* Quick Stats */}
          <div className="bg-gray-50 rounded-lg p-6">
            <h3 className="font-semibold text-gray-900 mb-4">Statistics</h3>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-gray-500">Revisions</dt>
                <dd className="font-medium">{revisions.length}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Findings</dt>
                <dd className="font-medium">{findings.length}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Pending Sign-offs</dt>
                <dd className="font-medium">{pendingSignoffs}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Current Revision</dt>
                <dd className="font-medium">{latestRevision?.version || '—'}</dd>
              </div>
            </dl>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ContentDetail;
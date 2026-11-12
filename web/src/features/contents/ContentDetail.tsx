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
  type ReviewPreviewResponse,
  uploadVisualAsset,
  type VisualAssetUploadResponse,
} from '../../lib/data';
import { createReviewPreview, confirmReviewPreview } from '../../lib/data';

interface FindingDisplay extends FindingWithDecision {
  displayQuote: string;
}

interface UploadedVisualAsset extends VisualAssetUploadResponse {
  fileName: string;
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

function ReviewPreviewDialog({
  preview, imageConsent, confirming, confirmationError, onImageConsentChange, onConfirm, onCancel,
}: {
  preview: ReviewPreviewResponse;
  imageConsent: boolean;
  confirming: boolean;
  confirmationError: string | null;
  onImageConsentChange: (checked: boolean) => void;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const missingImagePreview = preview.image_consent_required
    && preview.assets.some(asset => !asset.preview_url);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="presentation">
      <section role="dialog" aria-modal="true" aria-labelledby="review-preview-title" className="w-full max-w-4xl max-h-[92vh] overflow-hidden rounded-xl bg-white shadow-2xl flex flex-col">
        <header className="flex items-start justify-between gap-4 border-b border-gray-200 p-5">
          <div>
            <h2 id="review-preview-title" className="text-lg font-semibold text-gray-900">Review preview</h2>
            <p className="mt-1 text-sm text-gray-500">No AI provider has been called. Check the redacted content and disclosures before confirming.</p>
          </div>
          <button onClick={onCancel} className="rounded-lg px-3 py-1 text-gray-500 hover:bg-gray-100" aria-label="Close preview">×</button>
        </header>
        <div className="overflow-y-auto p-5 space-y-5">
          <div className="flex flex-wrap items-center gap-3 text-xs text-gray-600">
            <span className="rounded-full bg-green-50 px-3 py-1 font-medium text-green-800">{preview.redaction_summary.total_matches} sensitive matches masked</span>
            <span>Expires {new Date(preview.expires_at).toLocaleString()}</span>
            <span>Policy v{preview.redaction_summary.policy_version}</span>
          </div>
          <section>
            <h3 className="mb-2 font-semibold text-gray-900">Redacted draft sent for review</h3>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-gray-50 p-4 text-sm text-gray-800">{preview.redacted_draft}</pre>
          </section>
          <section className="space-y-2">
            <h3 className="font-semibold text-gray-900">Text provider request</h3>
            <details className="rounded-lg border border-gray-200 p-3">
              <summary className="cursor-pointer text-sm font-medium text-gray-700">Inspect exact system instruction and user prompt</summary>
              <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-gray-500">System instruction</p>
              <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-gray-50 p-3 text-xs text-gray-700">{preview.text_provider_preview.system_instruction}</pre>
              <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-gray-500">User content</p>
              <pre className="mt-1 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-gray-50 p-3 text-xs text-gray-700">{preview.text_provider_preview.user_content}</pre>
            </details>
          </section>
          {preview.assets.length > 0 && (
            <section className="space-y-3">
              <h3 className="font-semibold text-gray-900">Attached images ({preview.assets.length})</h3>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {preview.assets.map(asset => (
                  <figure key={asset.id} className="overflow-hidden rounded-lg border border-gray-200 bg-gray-50">
                    {asset.preview_url ? <img src={asset.preview_url} alt="Attached visual asset" className="h-36 w-full object-contain bg-gray-100" /> : <div className="flex h-36 items-center justify-center px-3 text-center text-xs text-red-700">Image preview unavailable</div>}
                    <figcaption className="p-2 text-xs text-gray-600">{asset.width} × {asset.height} · {asset.mime_type}</figcaption>
                  </figure>
                ))}
              </div>
            </section>
          )}
          {preview.vision_provider_preview && (
            <section className="space-y-2">
              <h3 className="font-semibold text-gray-900">Vision provider request</h3>
              <details className="rounded-lg border border-gray-200 p-3">
                <summary className="cursor-pointer text-sm font-medium text-gray-700">Inspect exact visual-analysis prompt</summary>
                <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-gray-500">System instruction</p>
                <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-gray-50 p-3 text-xs text-gray-700">{preview.vision_provider_preview.system_instruction}</pre>
                <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-gray-500">User content</p>
                <pre className="mt-1 max-h-56 overflow-auto whitespace-pre-wrap rounded bg-gray-50 p-3 text-xs text-gray-700">{preview.vision_provider_preview.user_content}</pre>
              </details>
            </section>
          )}
          {confirmationError && (
            <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
              {confirmationError}
            </p>
          )}
          {preview.image_consent_required ? (
            <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 space-y-3">
              <div>
                <h3 className="font-semibold text-amber-900">Image disclosure</h3>
                <p className="mt-1 text-sm text-amber-900">The attached images shown above will be sent to the vision AI provider in their stored form. Image pixels are not OCR-redacted. Text fields and visual guidelines are redacted separately.</p>
              </div>
              <label className="flex items-start gap-3 text-sm text-amber-950">
                <input type="checkbox" checked={imageConsent} onChange={event => onImageConsentChange(event.target.checked)} disabled={confirming || missingImagePreview} className="mt-1 h-4 w-4" />
                <span>I have reviewed the attached images and explicitly consent to sending them in their stored form to the AI vision provider for this review.</span>
              </label>
              {missingImagePreview && <p className="text-sm font-medium text-red-700">The image preview could not be loaded. Close this dialog and try again; consent is disabled.</p>}
            </div>
          ) : preview.assets.length > 0 ? (
            <p className="rounded-lg bg-blue-50 p-3 text-sm text-blue-900">Images are attached for local visual checks. This preview contains no vision-provider request, so image bytes will not be sent to an AI provider.</p>
          ) : null}
        </div>
        <footer className="flex flex-wrap justify-end gap-3 border-t border-gray-200 p-5">
          <button onClick={onCancel} disabled={confirming} className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50">Cancel</button>
          <button onClick={onConfirm} disabled={confirming || missingImagePreview || (preview.image_consent_required && !imageConsent)} className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-dark disabled:cursor-not-allowed disabled:opacity-50">
            {confirming ? 'Confirming...' : 'Confirm & Run Review'}
          </button>
        </footer>
      </section>
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
  reviewActionError,
}: {
  latestReview: Review | null;
  findings: FindingDisplay[];
  startingReview: boolean;
  handleStartReview: () => void;
  isContentEditable: boolean;
  reviewActionError: string | null;
}) {
  if (!latestReview) {
    return (
      <div className="text-center py-8 text-gray-500">
        <p>No review started for this revision.</p>
        {isContentEditable && (
          <>
          <button
            type="button"
            onClick={() => { void handleStartReview(); }}
            disabled={startingReview}
            aria-busy={startingReview}
            className="mt-4 inline-flex items-center justify-center px-4 py-2 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary-dark focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 disabled:cursor-wait disabled:opacity-60"
          >
            {startingReview ? 'Preparing review preview...' : 'Start Review'}
          </button>
          <p className="mt-2 text-xs text-gray-500">A privacy preview will appear before any AI provider is called.</p>
          {reviewActionError && <p role="alert" className="mx-auto mt-3 max-w-xl rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-left text-sm text-red-800">Could not prepare review preview: {reviewActionError}</p>}
          </>
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
      {reviewActionError && <p role="alert" className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">Could not prepare review preview: {reviewActionError}</p>}
      <button
        onClick={() => handleStartReview()}
        disabled={startingReview}
        className="mt-3 px-4 py-2 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary-dark disabled:opacity-50"
      >
        {startingReview ? 'Preparing preview...' : 'Preview & Retry'}
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
  const [reviewActionError, setReviewActionError] = useState<string | null>(null);
  const [reviewPreview, setReviewPreview] = useState<ReviewPreviewResponse | null>(null);
  const [imageConsent, setImageConsent] = useState(false);
  const [confirmingPreview, setConfirmingPreview] = useState(false);
  const [previewConfirmError, setPreviewConfirmError] = useState<string | null>(null);
  const [applyingDecisions, setApplyingDecisions] = useState(false);
  const [uploadedVisualAssets, setUploadedVisualAssets] = useState<UploadedVisualAsset[]>([]);
  const [isUploadingVisualAssets, setIsUploadingVisualAssets] = useState(false);
  const [visualUploadProgress, setVisualUploadProgress] = useState<{ completed: number; total: number } | null>(null);
  const [visualUploadError, setVisualUploadError] = useState<string | null>(null);

  // Editor visibility state (separate from mutation state)
  const [isRevisionEditorOpen, setIsRevisionEditorOpen] = useState(false);

  // Single-submission guards
  const submittingRef = useRef(false);
  const creatingRevisionRef = useRef(false);
  const startingReviewRef = useRef(false);
  const confirmingPreviewRef = useRef(false);
  const applyingDecisionsRef = useRef(false);
  const uploadingVisualAssetsRef = useRef(false);
  const visualUploadInputRef = useRef<HTMLInputElement>(null);

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

  // Selected revision for viewing history
  const [selectedRevisionId, setSelectedRevisionId] = useState<string | null>(null);
  const [selectedRevision, setSelectedRevision] = useState<Revision | null>(null);

  // Select a revision for viewing
  const handleSelectRevision = useCallback((revision: Revision) => {
    if (selectedRevisionId === revision.id) {
      // Deselect if clicking the same revision, fall back to latest
      setSelectedRevisionId(latestRevision?.id ?? null);
      setSelectedRevision(latestRevision);
    } else {
      setSelectedRevisionId(revision.id);
      setSelectedRevision(revision);
    }
  }, [latestRevision]);

  useEffect(() => {
    setReviewPreview(null);
    setImageConsent(false);
    setPreviewConfirmError(null);
    setReviewActionError(null);
  }, [contentId]);

  // Uploaded previews and errors belong to one exact revision.
  useEffect(() => {
    setUploadedVisualAssets([]);
    setVisualUploadError(null);
    setVisualUploadProgress(null);
  }, [contentId, latestRevision?.id]);

  // Reset selection when content changes
  useEffect(() => {
    setSelectedRevisionId(latestRevision?.id ?? null);
    setSelectedRevision(latestRevision);
  }, [contentId, latestRevision]);

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

  const loadReviewData = useCallback(async (requestedRevisionId?: string) => {
    const revisionId = requestedRevisionId ?? latestRevision?.id;

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

        // Publish terminal status only after its findings have loaded. The
        // status effect stops polling; publishing it earlier invalidates this
        // in-flight request and discards the findings response.
        setFindings(findingsData as FindingDisplay[]);
        setPendingSignoffs(signoffs.length);
        setLatestReview(review);
        stopPolling();
      } else {
        setLatestReview(review);
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
}, [latestReview?.status, startPolling, stopPolling]);
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

  const handleVisualImageSelection = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.currentTarget.files ?? []);
    // Clear the input so selecting the same file again triggers another change event.
    event.currentTarget.value = '';
    if (files.length === 0) return;
    if (!content || !latestRevision?.id) {
      setVisualUploadError('Create a revision before attaching images.');
      return;
    }
    if (selectedRevisionId !== latestRevision.id) {
      setVisualUploadError('Select the latest revision before attaching images. Visual reviews only process the latest revision.');
      return;
    }
    if (latestReview?.status === 'queued' || latestReview?.status === 'running') {
      setVisualUploadError('Images cannot be changed while a review is queued or running.');
      return;
    }
    if (uploadingVisualAssetsRef.current) return;

    uploadingVisualAssetsRef.current = true;
    setIsUploadingVisualAssets(true);
    setVisualUploadError(null);
    setVisualUploadProgress({ completed: 0, total: files.length });
    const failures: string[] = [];
    let uploadedCount = 0;

    try {
      for (let index = 0; index < files.length; index += 1) {
        const file = files[index];
        try {
          const result = await uploadVisualAsset(file, content.id, latestRevision.id);
          setUploadedVisualAssets(current => [
            ...current.filter(asset => asset.asset_id !== result.asset_id),
            { ...result, fileName: file.name },
          ]);
          uploadedCount += 1;
        } catch (err) {
          failures.push(`${file.name}: ${err instanceof Error ? err.message : 'Upload failed'}`);
        } finally {
          setVisualUploadProgress({ completed: index + 1, total: files.length });
        }
      }

      if (uploadedCount > 0) {
        // A newly attached image changes the review input set. Invalidate any
        // preview token created before the upload; it cannot safely be confirmed.
        setReviewPreview(null);
        setImageConsent(false);
        setPreviewConfirmError(null);
        stopPolling();
        setLatestReview(null);
        setFindings([]);
        setPendingSignoffs(0);
        setReviewActionError(null);
      }
      if (failures.length > 0) {
        setVisualUploadError(failures.join(' '));
      }
    } finally {
      setIsUploadingVisualAssets(false);
      setVisualUploadProgress(null);
      uploadingVisualAssetsRef.current = false;
    }
  };

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

  const handleStartReview = async (revisionId?: string) => {
    if (startingReviewRef.current) return;

    startingReviewRef.current = true;
    setStartingReview(true);
    setReviewActionError(null);
    setPreviewConfirmError(null);
    setToastError(null);

    // Prefer the explicitly selected revision, then fall back to the loaded
    // revision objects. Never silently return from a visible Start Review action.
    const targetRevisionId = revisionId ?? selectedRevisionId ?? selectedRevision?.id ?? latestRevision?.id;
    if (!targetRevisionId) {
      setReviewActionError('This content has no loaded revision yet. Reload the content and try again.');
      setStartingReview(false);
      startingReviewRef.current = false;
      return;
    }

    try {
      const preview = await createReviewPreview(targetRevisionId);
      setReviewPreview(preview);
      setImageConsent(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to prepare review preview';
      setReviewActionError(message);
    } finally {
      setStartingReview(false);
      startingReviewRef.current = false;
    }
  };

  const handleConfirmReview = async () => {
    if (!reviewPreview || confirmingPreviewRef.current) return;
    if (reviewPreview.image_consent_required && !imageConsent) {
      setPreviewConfirmError('Explicit image consent is required before this review can start.');
      return;
    }
    confirmingPreviewRef.current = true;
    setConfirmingPreview(true);
    setPreviewConfirmError(null);
    setToastError(null);
    try {
      await confirmReviewPreview(reviewPreview.preview_id, reviewPreview.confirmation_token, imageConsent);
      const confirmedRevisionId = reviewPreview.revision_id;
      setReviewPreview(null);
      setImageConsent(false);
      setPreviewConfirmError(null);
      await loadReviewData(confirmedRevisionId);
    } catch (err) {
      const errorObject = err && typeof err === 'object'
        ? err as { message?: unknown; reason?: unknown; status?: unknown }
        : undefined;
      const message = typeof errorObject?.message === 'string'
        ? errorObject.message
        : 'Failed to confirm review';
      const reason = typeof errorObject?.reason === 'string' ? errorObject.reason : undefined;

      if (reason === 'preview_already_consumed') {
        const confirmedRevisionId = reviewPreview.revision_id;
        setReviewPreview(null);
        setImageConsent(false);
        setPreviewConfirmError(null);
        await loadReviewData(confirmedRevisionId);
        setToastError('This preview was already confirmed. Review status has been refreshed.');
      } else if (reason === 'preview_expired') {
        setReviewPreview(null);
        setImageConsent(false);
        setPreviewConfirmError(null);
        setToastError('This preview expired. Click Start Review again to prepare a fresh preview.');
      } else if ([
        'preview_integrity_failed',
        'assets_changed',
        'asset_changed',
        'revision_changed',
        'not_latest_revision',
        'revision_not_editable',
        'active_kit_changed',
        'kit_changed',
        'policy_changed',
        'preview_not_available',
      ].includes(reason || '')) {
        setReviewPreview(null);
        setImageConsent(false);
        setPreviewConfirmError(null);
        const guidance = reason === 'assets_changed' || reason === 'asset_changed'
          ? 'Attached images changed after this preview was created.'
          : 'The revision, brand kit, or confidentiality settings changed after this preview was created.';
        setToastError(`${guidance} No review was started. Click Start Review again to prepare a fresh preview using the current inputs.`);
      } else {
        // Keep unexpected 4xx/5xx errors inside the dialog; the page-level
        // toast sits behind the modal and previously made these failures look inert.
        setPreviewConfirmError(message);
      }
    } finally {
      setConfirmingPreview(false);
      confirmingPreviewRef.current = false;
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
        await handleStartReview(newLatestRevision.id);
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
  const canUploadVisualAssets = session.currentRoles.includes('creator') || session.currentRoles.includes('owner');
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
              {revisions.map(rev => {
                const isSelected = selectedRevisionId === rev.id;
                const isLatest = latestRevision?.id === rev.id;
                return (
                  <button
                    key={rev.id}
                    onClick={() => handleSelectRevision(rev)}
                    className={`w-full px-4 py-3 text-left hover:bg-gray-50 transition-colors ${
                      isSelected ? 'bg-primary-50 border-l-2 border-primary' :
                      isLatest ? 'bg-blue-50' :
                      'hover:bg-gray-50'
                    } transition-colors border-l-2 border-transparent`}
                    style={{ cursor: 'pointer' }}
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="font-medium text-gray-900">Revision {rev.version}</span>
                        <span className="ml-2 text-xs text-gray-500">{new Date(rev.created_at).toLocaleString()}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        {isLatest && (
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">
                            Latest
                          </span>
                        )}
                        {isSelected && !isLatest && (
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-primary-100 text-primary-800">
                            Viewing
                          </span>
                        )}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Content body */}
          <div className="bg-white border border-gray-200 rounded-lg">
            <div className="p-4 border-b border-gray-200 flex items-center justify-between">
              <h2 className="font-semibold text-gray-900">Content</h2>
              {selectedRevisionId && selectedRevisionId !== latestRevision?.id && (
                <span className="text-xs text-gray-500 bg-gray-100 px-2 py-0.5 rounded">
                  Viewing Revision {selectedRevision?.version} (not latest)
                </span>
              )}
            </div>
            <div className="p-6">
              <pre className="whitespace-pre-wrap font-mono text-sm text-gray-800 bg-gray-50 p-4 rounded-lg max-h-96 overflow-y-auto">
                {(selectedRevision?.body) || latestRevision?.body || 'No content'}
              </pre>
            </div>
          </div>

          {/* Visual assets for Improvement 1 */}
          {isContentEditable && canUploadVisualAssets && latestRevision && (
            <section className="bg-white border border-gray-200 rounded-lg" aria-labelledby="visual-assets-title">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 p-4">
                <div>
                  <h2 id="visual-assets-title" className="font-semibold text-gray-900">Visual Assets</h2>
                  <p className="mt-1 text-xs text-gray-500">Images attached to latest revision {latestRevision.version}</p>
                </div>
                <button
                  type="button"
                  onClick={() => visualUploadInputRef.current?.click()}
                  disabled={isUploadingVisualAssets || selectedRevisionId !== latestRevision.id || latestReview?.status === 'queued' || latestReview?.status === 'running'}
                  className="inline-flex items-center justify-center rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-dark disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isUploadingVisualAssets ? 'Uploading images...' : 'Upload images'}
                </button>
                <input
                  ref={visualUploadInputRef}
                  aria-label="Choose images to upload"
                  type="file"
                  accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp"
                  multiple
                  className="sr-only"
                  onChange={handleVisualImageSelection}
                  disabled={isUploadingVisualAssets || selectedRevisionId !== latestRevision.id || latestReview?.status === 'queued' || latestReview?.status === 'running'}
                />
              </div>
              <div className="space-y-3 p-4">
                <p className="text-xs text-gray-500">PNG, JPG/JPEG, and WebP (10 MB maximum per image). Uploading attaches images to this revision; it does not send them to an AI provider. Image metadata is removed before private storage. The privacy preview will disclose image use and request consent before original image bytes are sent.</p>
                {selectedRevisionId !== latestRevision.id && (
                  <p className="text-sm text-amber-800" role="status">Select the latest revision to attach images for visual review.</p>
                )}
                {(latestReview?.status === 'queued' || latestReview?.status === 'running') && (
                  <p className="text-sm text-amber-800" role="status">Image uploads are paused while this revision is being reviewed.</p>
                )}
                {visualUploadProgress && (
                  <p className="text-sm text-gray-600" role="status">Uploading image {visualUploadProgress.completed} of {visualUploadProgress.total}...</p>
                )}
                {visualUploadError && <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">{visualUploadError}</p>}
                {uploadedVisualAssets.length === 0 ? (
                  <p className="text-sm text-gray-500">No images uploaded in this session yet. Existing linked images will appear in the review privacy preview.</p>
                ) : (
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                    {uploadedVisualAssets.map(asset => (
                      <figure key={asset.asset_id} className="overflow-hidden rounded-lg border border-gray-200 bg-gray-50">
                        <img src={asset.signed_url} alt={asset.fileName} className="h-32 w-full bg-gray-100 object-contain" />
                        <figcaption className="space-y-1 p-2">
                          <p className="truncate text-xs font-medium text-gray-800" title={asset.fileName}>{asset.fileName}</p>
                          <p className="text-xs text-gray-500">{asset.width} x {asset.height} | {asset.mime_type}</p>
                        </figcaption>
                      </figure>
                    ))}
                  </div>
                )}
              </div>
            </section>
          )}

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
                reviewActionError={reviewActionError}
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
                onClick={() => handleStartReview()}
                disabled={startingReview}
                className="w-full px-4 py-2 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary-dark disabled:opacity-50"
              >
                {startingReview ? 'Preparing preview...' : 'Preview & Retry'}
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
      {reviewPreview && (
        <ReviewPreviewDialog
          preview={reviewPreview}
          imageConsent={imageConsent}
          confirming={confirmingPreview}
          confirmationError={previewConfirmError}
          onImageConsentChange={setImageConsent}
          onConfirm={handleConfirmReview}
          onCancel={() => {
            if (!confirmingPreview) {
              setReviewPreview(null);
              setImageConsent(false);
              setPreviewConfirmError(null);
            }
          }}
        />
      )}
    </div>
  );
}

export default ContentDetail;
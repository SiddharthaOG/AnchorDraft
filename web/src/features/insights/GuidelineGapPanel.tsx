import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthProvider';
import {
  acceptGuidelineSuggestion,
  confirmGuidelineSuggestionPreview,
  createGuidelineSuggestionPreview,
  getGuidelineGapAnalytics,
  rejectGuidelineSuggestion,
  type GuidelineGapAnalytics,
  type GuidelineSuggestionPreview,
} from '../../lib/data';

export function GuidelineGapPanel() {
  const { hasAnyRole } = useAuth();
  const canManage = hasAnyRole(['manager', 'owner']);
  const [analytics, setAnalytics] = useState<GuidelineGapAnalytics | null>(null);
  const [preview, setPreview] = useState<GuidelineSuggestionPreview | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [rejectionReasons, setRejectionReasons] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    if (!canManage) return;
    setIsLoading(true);
    setError(null);
    try {
      setAnalytics(await getGuidelineGapAnalytics());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load guideline-gap analytics');
    } finally {
      setIsLoading(false);
    }
  }, [canManage]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!canManage) return null;

  const handlePreview = async (ruleKey: string) => {
    setBusyKey(ruleKey);
    setError(null);
    setNotice(null);
    try {
      setPreview(await createGuidelineSuggestionPreview(ruleKey));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to prepare suggestion preview');
    } finally {
      setBusyKey(null);
    }
  };

  const handleConfirmPreview = async () => {
    if (!preview) return;
    setBusyKey(preview.preview_id);
    setError(null);
    try {
      const suggestion = await confirmGuidelineSuggestionPreview(
        preview.preview_id,
        preview.confirmation_token,
      );
      setNotice('A wording proposal was generated for ' + suggestion.rule_key + '. Review it below.');
      setPreview(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to generate wording proposal');
    } finally {
      setBusyKey(null);
    }
  };

  const handleAccept = async (suggestionId: string) => {
    setBusyKey(suggestionId);
    setError(null);
    try {
      const result = await acceptGuidelineSuggestion(suggestionId);
      setNotice('Accepted. Brand kit version ' + result.version + ' is now active.');
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to accept suggestion');
    } finally {
      setBusyKey(null);
    }
  };

  const handleReject = async (suggestionId: string) => {
    setBusyKey(suggestionId);
    setError(null);
    try {
      await rejectGuidelineSuggestion(suggestionId, rejectionReasons[suggestionId]);
      setNotice('Suggestion rejected and recorded.');
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to reject suggestion');
    } finally {
      setBusyKey(null);
    }
  };

  return (
    <section className="bg-white rounded-lg shadow p-6 space-y-5" aria-labelledby="guideline-gap-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="guideline-gap-heading" className="text-lg font-semibold text-gray-900">Guideline gaps</h2>
          <p className="text-sm text-gray-500 mt-1">
            Repeated dismissals can signal unclear rules. Proposals never change a kit until a manager or owner accepts them.
          </p>
          {analytics?.kit && (
            <p className="text-xs text-gray-400 mt-1">Active kit: {analytics.kit.name} · Version {analytics.kit.version}</p>
          )}
        </div>
        <button
          type="button"
          onClick={() => void load()}
          disabled={isLoading}
          className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
        >
          {isLoading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {error && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}
      {notice && (
        <div role="status" className="rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-800">
          {notice}
        </div>
      )}
      {isLoading && !analytics && <p className="text-sm text-gray-500">Loading guideline-gap analytics…</p>}
      {!isLoading && analytics && !analytics.kit && (
        <p className="text-sm text-gray-500">No active brand kit is available for this organisation.</p>
      )}
      {analytics?.kit && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3" aria-label="Guideline feedback summary">
            <div className="rounded-lg border border-gray-200 p-3">
              <p className="text-xs text-gray-500">Active guidelines</p>
              <p className="mt-1 text-xl font-semibold text-gray-900">{analytics.rules.length}</p>
            </div>
            <div className="rounded-lg border border-gray-200 p-3">
              <p className="text-xs text-gray-500">Guidelines with reviewer decisions</p>
              <p className="mt-1 text-xl font-semibold text-gray-900">
                {analytics.rules.filter((rule) => rule.decided > 0).length} / {analytics.rules.length}
              </p>
            </div>
            <div className="rounded-lg border border-gray-200 p-3">
              <p className="text-xs text-gray-500">Potential guideline gaps</p>
              <p className="mt-1 text-xl font-semibold text-gray-900">{analytics.gaps.length}</p>
            </div>
          </div>

          {analytics.rules.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-sm font-semibold text-gray-900">Reviewer decision coverage</h3>
              <div className="overflow-x-auto rounded-lg border border-gray-200">
                <table className="min-w-full divide-y divide-gray-200 text-sm">
                  <thead className="bg-gray-50 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
                    <tr>
                      <th scope="col" className="px-3 py-2">Guideline</th>
                      <th scope="col" className="px-3 py-2">Decisions</th>
                      <th scope="col" className="px-3 py-2">Dismissal rate</th>
                      <th scope="col" className="px-3 py-2">Assessment</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 bg-white">
                    {analytics.rules.map((rule) => (
                      <tr key={rule.rule_key}>
                        <td className="px-3 py-2">
                          <span className="font-mono text-xs text-gray-500">{rule.rule_key}</span>
                          <span className="ml-2 text-gray-800">{rule.title}</span>
                        </td>
                        <td className="px-3 py-2 tabular-nums text-gray-700">{rule.decided}</td>
                        <td className="px-3 py-2 tabular-nums text-gray-700">{Math.round(rule.dismissal_rate * 100)}%</td>
                        <td className="px-3 py-2 text-xs text-gray-600">
                          {rule.is_gap ? 'Potential gap' : rule.decided < 5 ? 'Insufficient evidence' : 'No gap threshold met'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-gray-500">
                Low decision counts are shown as insufficient evidence, not as proof that a guideline is missing.
              </p>
            </div>
          )}
        </>
      )}

      {analytics && analytics.kit && analytics.gaps.length === 0 && (
        <div className="rounded-lg bg-gray-50 p-5 text-sm text-gray-600">
          No guideline gaps meet the current evidence threshold (at least 5 decisions, 50% dismissal rate, and a repeated reason cluster).
        </div>
      )}

      {analytics?.gaps.map((gap) => (
        <article key={gap.rule_key} className="border border-amber-200 rounded-lg p-4 space-y-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-semibold text-gray-900">{gap.rule_key} · {gap.title}</h3>
                <span className="text-xs rounded-full bg-amber-100 px-2 py-0.5 text-amber-800">Needs clarity review</span>
              </div>
              <p className="text-xs text-gray-500 mt-1">{gap.category} · {gap.decided} decisions · {gap.dismissed} dismissed · {Math.round(gap.dismissal_rate * 100)}% dismissal rate</p>
            </div>
          </div>
          <div className="rounded-md bg-gray-50 p-3">
            <p className="text-xs font-medium uppercase tracking-wide text-gray-500 mb-1">Current guideline</p>
            <p className="text-sm text-gray-800 whitespace-pre-wrap">{gap.guideline_text}</p>
          </div>

          <div>
            <p className="text-sm font-medium text-gray-800 mb-2">Dismissal reason groups</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {gap.reason_clusters.map((cluster, index) => (
                <div key={gap.rule_key + '-' + index} className="rounded-md border border-gray-200 p-3">
                  <div className="flex justify-between gap-2">
                    <span className="text-sm font-medium text-gray-800">{cluster.theme}</span>
                    <span className="text-xs text-gray-500">{cluster.count} reasons</span>
                  </div>
                  <ul className="mt-2 space-y-1">
                    {cluster.examples.map((example, exampleIndex) => (
                      <li key={exampleIndex} className="text-xs text-gray-600">“{example}”</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>

          {gap.suggestion?.status === 'pending' ? (
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 space-y-3">
              <div className="text-xs font-semibold uppercase tracking-wide text-blue-800">Pending human decision · kit v{gap.suggestion.source_kit_version}</div>
              <p className="text-xs text-blue-700">Generated with {gap.suggestion.model || gap.suggestion.provider || "configured provider"}</p>
              <div>
                <p className="text-xs font-medium text-gray-500 mb-1">Suggested wording</p>
                <p className="text-sm text-gray-900 whitespace-pre-wrap">{gap.suggestion.suggested_text}</p>
              </div>
              <p className="text-sm text-gray-700">{gap.suggestion.explanation}</p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void handleAccept(gap.suggestion!.id)}
                  disabled={busyKey === gap.suggestion.id}
                  className="px-3 py-2 rounded-lg bg-primary text-white text-sm font-medium hover:opacity-90 disabled:opacity-50"
                >
                  {busyKey === gap.suggestion.id ? 'Working…' : 'Accept and create new kit version'}
                </button>
                <button
                  type="button"
                  onClick={() => void handleReject(gap.suggestion!.id)}
                  disabled={busyKey === gap.suggestion.id}
                  className="px-3 py-2 rounded-lg border border-gray-300 text-gray-700 text-sm font-medium hover:bg-white disabled:opacity-50"
                >
                  Reject
                </button>
                <input
                  aria-label={'Optional rejection reason for ' + gap.rule_key}
                  value={rejectionReasons[gap.suggestion.id] || ''}
                  onChange={(event) => setRejectionReasons((current) => ({ ...current, [gap.suggestion!.id]: event.target.value }))}
                  placeholder="Optional rejection reason"
                  maxLength={1000}
                  className="min-w-48 flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm"
                />
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => void handlePreview(gap.rule_key)}
              disabled={busyKey === gap.rule_key}
              className="px-3 py-2 rounded-lg border border-primary text-primary text-sm font-medium hover:bg-primary-light disabled:opacity-50"
            >
              {busyKey === gap.rule_key ? 'Preparing…' : 'Preview wording suggestion'}
            </button>
          )}
        </article>
      ))}

      {preview && (
        <div className="rounded-lg border border-indigo-200 bg-indigo-50 p-4 space-y-3">
          <div>
            <h3 className="font-semibold text-gray-900">Review exactly what will leave AnchorDraft</h3>
            <p className="text-xs text-gray-600 mt-1">
              No provider call has happened yet. Confirming sends only the redacted content shown below. This preview expires at {new Date(preview.expires_at).toLocaleTimeString()}.
            </p>
            <p className="text-xs text-gray-600 mt-1">
              {preview.redaction_summary.total_matches} redactions · policy version {preview.redaction_summary.policy_version} · {preview.redaction_summary.original_chars} original characters / {preview.redaction_summary.redacted_chars} redacted characters
            </p>
          </div>
          <details>
            <summary className="cursor-pointer text-sm font-medium text-gray-800">System instruction</summary>
            <pre className="mt-2 whitespace-pre-wrap break-words rounded bg-white p-3 text-xs text-gray-700">{preview.system_instruction}</pre>
          </details>
          <div>
            <p className="text-xs font-medium text-gray-500 mb-1">Exact redacted user content</p>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded bg-white p-3 text-xs text-gray-700">{preview.user_content}</pre>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void handleConfirmPreview()}
              disabled={busyKey === preview.preview_id}
              className="px-3 py-2 rounded-lg bg-primary text-white text-sm font-medium hover:opacity-90 disabled:opacity-50"
            >
              {busyKey === preview.preview_id ? 'Generating…' : 'Confirm and generate suggestion'}
            </button>
            <button
              type="button"
              onClick={() => setPreview(null)}
              disabled={busyKey === preview.preview_id}
              className="px-3 py-2 rounded-lg border border-gray-300 text-gray-700 text-sm font-medium hover:bg-white"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

export default GuidelineGapPanel;

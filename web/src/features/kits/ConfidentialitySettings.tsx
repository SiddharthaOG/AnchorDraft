import { useEffect, useState } from 'react';
import { getConfidentialityPolicy, updateConfidentialityPolicy, type ConfidentialityPolicy } from '../../lib/confidentiality';

const switches: { key: keyof ConfidentialityPolicy; label: string; description: string }[] = [
  { key: 'redact_emails', label: 'Email addresses', description: 'Replace detected email addresses before AI processing.' },
  { key: 'redact_phones', label: 'Phone numbers', description: 'Replace detected phone numbers before AI processing.' },
  { key: 'redact_api_keys', label: 'API keys and credentials', description: 'Replace supported API-key patterns.' },
  { key: 'redact_jwts', label: 'JWTs', description: 'Replace JSON Web Tokens.' },
  { key: 'redact_credit_cards', label: 'Payment card numbers', description: 'Replace detected payment-card numbers.' },
];

export function ConfidentialitySettings() {
  const [policy, setPolicy] = useState<ConfidentialityPolicy | null>(null);
  const [termsText, setTermsText] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = async () => {
    setLoading(true); setError(null); setNotice(null);
    try {
      const value = await getConfidentialityPolicy();
      setPolicy(value);
      setTermsText(value.custom_terms.join('\n'));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load confidentiality settings.');
    } finally { setLoading(false); }
  };

  useEffect(() => { void load(); }, []);

  const save = async () => {
    if (!policy) return;
    const custom_terms = termsText.split(/\r?\n/).map(term => term.trim()).filter(Boolean);
    setSaving(true); setError(null); setNotice(null);
    try {
      const updated = await updateConfidentialityPolicy({ ...policy, custom_terms });
      setPolicy(updated);
      setTermsText(updated.custom_terms.join('\n'));
      setNotice(`Saved as policy version ${updated.version}. New previews will use these settings; existing previews must be recreated.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save confidentiality settings.');
    } finally { setSaving(false); }
  };

  if (loading) return <p className="text-sm text-gray-500" role="status">Loading confidentiality settings…</p>;
  if (!policy) return <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error || 'Settings unavailable.'}<button onClick={() => void load()} className="ml-3 underline">Retry</button></div>;

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm" aria-labelledby="confidentiality-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="confidentiality-heading" className="text-lg font-semibold text-gray-900">Confidentiality controls</h2>
          <p className="mt-1 max-w-2xl text-sm text-gray-600">Configure what AnchorDraft redacts from review inputs before any AI provider is called. These settings apply to your organisation.</p>
        </div>
        <span className="rounded-full bg-gray-100 px-3 py-1 text-xs font-medium text-gray-600">Policy v{policy.version}</span>
      </div>
      <label className="mt-6 flex items-start gap-3 rounded-lg border border-gray-200 p-4">
        <input type="checkbox" checked={policy.enabled} onChange={e => setPolicy({ ...policy, enabled: e.target.checked })} className="mt-1" />
        <span><span className="block text-sm font-medium text-gray-900">Enable confidentiality redaction</span><span className="block text-sm text-gray-500">When disabled, no configured values are redacted. Use this only if your organisation explicitly accepts that risk.</span></span>
      </label>
      <div className="mt-5 space-y-3">
        {switches.map(item => (
          <label key={item.key} className="flex items-start justify-between gap-4 border-b border-gray-100 pb-3">
            <span><span className="block text-sm font-medium text-gray-800">{item.label}</span><span className="block text-xs text-gray-500">{item.description}</span></span>
            <input type="checkbox" checked={Boolean(policy[item.key])} disabled={!policy.enabled} onChange={e => setPolicy({ ...policy, [item.key]: e.target.checked })} aria-label={item.label} />
          </label>
        ))}
      </div>
      <div className="mt-6">
        <label htmlFor="confidentiality-terms" className="block text-sm font-semibold text-gray-900">Organisation-specific terms</label>
        <p className="mt-1 text-sm text-gray-500">One term per line. Matching is case-insensitive. Add project codenames, internal identifiers, confidential phrases, or other values that generic detectors cannot know.</p>
        <textarea id="confidentiality-terms" value={termsText} onChange={e => setTermsText(e.target.value)} rows={7} maxLength={20500} disabled={!policy.enabled} placeholder={'ORCHID-VAULT-ALPHA\nNEVER-SEND-ORIGINAL-TEXT-7F92'} className="mt-3 w-full rounded-lg border border-gray-300 px-3 py-2 font-mono text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:bg-gray-50" />
        <p className="mt-1 text-xs text-gray-500">{termsText.split(/\r?\n/).filter(term => term.trim()).length} terms · up to 500 terms, 256 characters each</p>
      </div>
      {error && <p role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      {notice && <p role="status" className="mt-4 rounded-lg bg-green-50 p-3 text-sm text-green-800">{notice}</p>}
      <div className="mt-5 flex items-center justify-between gap-3">
        <p className="text-xs text-gray-500">Saving increments the policy version and invalidates previews made under the previous policy.</p>
        <button onClick={() => void save()} disabled={saving} className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary-dark disabled:cursor-not-allowed disabled:opacity-50">{saving ? 'Saving…' : 'Save policy'}</button>
      </div>
    </section>
  );
}

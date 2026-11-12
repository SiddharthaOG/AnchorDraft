/** Kit detail page with rule/fact editor, lint panel, and activation workflow. */

import React, { useEffect, useState, useRef, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../features/auth/AuthProvider';
import { LoadingScreen } from '../../components/LoadingScreen';
import { VisualGuidelinesEditor } from './VisualGuidelinesEditor';
import {
  getBrandKits,
  getKitRules,
  getKitFacts,
  cloneKit,
  activateKit,
  createRule,
  updateRule,
  deleteRule,
  createFact,
  updateFact,
  deleteFact,
  lintKit,
  type BrandKit,
  type VisualGuidelines,
  updateKitVisualGuidelines,
  type Rule,
  type ApprovedFact,
  type KitLintResponse,
  type CreateRuleInput,
  type UpdateRuleInput,
  KitLintError,
} from '../../lib/data';

const CATEGORIES = ['tone', 'terminology', 'messaging', 'claim', 'fact', 'accessibility'];
const SEVERITIES = ['low', 'medium', 'high'];
const CHECK_KINDS = ['deterministic', 'llm'];

type Category = typeof CATEGORIES[number];
type Severity = typeof SEVERITIES[number];
type CheckKind = typeof CHECK_KINDS[number];

interface RuleFormData {
  rule_key: string;
  category: Category;
  title: string;
  guideline_text: string;
  severity: Severity;
  check_kind: CheckKind;
  config: Record<string, unknown> | null;
  needs_reviewer: boolean;
  example_bad: string;
  example_good: string;
}

interface FactFormData {
  fact_key: string;
  statement: string;
  source_note: string;
  valid_until: string;
}

const emptyRuleForm: RuleFormData = {
  rule_key: '',
  category: 'terminology',
  title: '',
  guideline_text: '',
  severity: 'medium',
  check_kind: 'deterministic',
  config: null,
  needs_reviewer: false,
  example_bad: '',
  example_good: '',
};

const emptyFactForm: FactFormData = {
  fact_key: '',
  statement: '',
  source_note: '',
  valid_until: '',
};

function StatusBadge({ status }: { status: BrandKit['status'] }) {
  const colors = {
    draft: 'bg-yellow-100 text-yellow-800',
    active: 'bg-green-100 text-green-800',
    archived: 'bg-gray-100 text-gray-800',
  };
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${colors[status]}`}>
      {status.charAt(0).toUpperCase() + status.slice(1)}
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
  onConfirm: () => void | Promise<void>;
  onCancel: () => void | Promise<void>;
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

function RuleEditor({
  rule,
  onSave,
  onCancel,
  isEditing,
  categories,
  severities,
  checkKinds,
}: {
  rule: Rule | null;
  onSave: (data: RuleFormData) => Promise<void>;
  onCancel: () => void | Promise<void>;
  isEditing: boolean;
  categories: Category[];
  severities: Severity[];
  checkKinds: CheckKind[];
}) {
  const [form, setForm] = useState<RuleFormData>(() => {
    if (!rule) return emptyRuleForm;
    return {
      rule_key: rule.rule_key,
      category: rule.category,
      title: rule.title,
      guideline_text: rule.guideline_text,
      severity: rule.severity,
      check_kind: rule.check_kind,
      config: rule.config,
      needs_reviewer: rule.needs_reviewer,
      example_bad: rule.example_bad || '',
      example_good: rule.example_good || '',
    };
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await onSave(form);
  };

  const handleChange = (field: keyof RuleFormData, value: unknown) => {
    setForm(prev => ({ ...prev, [field]: value }));
  };

  if (!isEditing && !rule) return null;

  return (
    <form onSubmit={handleSubmit} className="bg-white border border-gray-200 rounded-lg p-6 space-y-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-gray-900">{rule ? 'Edit Rule' : 'Add Rule'}</h3>
        <button
          type="button"
          onClick={onCancel}
          className="text-gray-400 hover:text-gray-600 text-xl leading-none p-1"
        >
          ×
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Rule Key *</label>
          <input
            type="text"
            value={form.rule_key}
            onChange={e => handleChange('rule_key', e.target.value.toUpperCase())}
            required
            disabled={!!rule}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent disabled:bg-gray-50"
            placeholder="e.g., TERM-01"
            pattern="^[A-Z0-9]+-[0-9]{2,3}$"
            title="Format: UPPERCASE-NUMBERS (e.g., TERM-01)"
          />
          {!rule && <p className="mt-1 text-xs text-gray-500">Format: PREFIX-NNN (e.g., TERM-01, CLAIM-12)</p>}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Category *</label>
          <select
            value={form.category}
            onChange={e => handleChange('category', e.target.value as Category)}
            required
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          >
            {categories.map(c => <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>)}
          </select>
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Title *</label>
        <input
          type="text"
          value={form.title}
          onChange={e => handleChange('title', e.target.value)}
          required
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          placeholder="Brief rule title"
          maxLength={200}
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Guideline Text *</label>
        <textarea
          value={form.guideline_text}
          onChange={e => handleChange('guideline_text', e.target.value)}
          required
          rows={3}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          placeholder="Full guideline wording shown to users and sent to the model"
          maxLength={5000}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Severity *</label>
          <select
            value={form.severity}
            onChange={e => handleChange('severity', e.target.value as Severity)}
            required
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          >
            {severities.map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Check Kind *</label>
          <select
            value={form.check_kind}
            onChange={e => handleChange('check_kind', e.target.value as CheckKind)}
            required
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          >
            {checkKinds.map(k => <option key={k} value={k}>{k === 'deterministic' ? 'Deterministic' : 'LLM-based'}</option>)}
          </select>
        </div>

        <div className="flex items-end">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={form.needs_reviewer}
              onChange={e => handleChange('needs_reviewer', e.target.checked)}
              className="w-4 h-4 text-primary border-gray-300 rounded focus:ring-primary focus:ring-2"
            />
            <span className="text-sm text-gray-700">Needs reviewer sign-off</span>
          </label>
        </div>
      </div>

      {form.check_kind === 'deterministic' && (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Config (JSON)</label>
          <textarea
            value={JSON.stringify(form.config || {}, null, 2)}
            onChange={e => {
              try {
                handleChange('config', e.target.value ? JSON.parse(e.target.value) : null);
              } catch {
                // Invalid JSON - keep previous value
              }
            }}
            rows={4}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent font-mono text-sm"
            placeholder='{"phrases": ["term1", "term2"]} or {"entries": [{"pattern": "regex", "replacement": "text"}]}'
          />
          <p className="mt-1 text-xs text-gray-500">Deterministic rules require valid config with phrases or entries</p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Bad Example</label>
          <textarea
            value={form.example_bad}
            onChange={e => handleChange('example_bad', e.target.value)}
            rows={2}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            placeholder="Example of violation"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Good Example</label>
          <textarea
            value={form.example_good}
            onChange={e => handleChange('example_good', e.target.value)}
            rows={2}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            placeholder="Example of correct usage"
          />
        </div>
      </div>

      <div className="flex justify-end gap-3 pt-4 border-t border-gray-200">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50"
        >
          Cancel
        </button>
        <button
          type="submit"
          className="px-4 py-2 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary-dark focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
        >
          {rule ? 'Save Changes' : 'Create Rule'}
        </button>
      </div>
    </form>
  );
}

function FactEditor({
  fact,
  onSave,
  onCancel,
  isEditing,
}: {
  fact: ApprovedFact | null;
  onSave: (data: FactFormData) => Promise<void>;
  onCancel: () => void | Promise<void>;
  isEditing: boolean;
}) {
  const [form, setForm] = useState<FactFormData>(() => {
    if (!fact) return emptyFactForm;
    return {
      fact_key: fact.fact_key,
      statement: fact.statement,
      source_note: fact.source_note,
      valid_until: fact.valid_until || '',
    };
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await onSave(form);
  };

  const handleChange = (field: keyof FactFormData, value: unknown) => {
    setForm(prev => ({ ...prev, [field]: value }));
  };

  if (!isEditing && !fact) return null;

  return (
    <form onSubmit={handleSubmit} className="bg-white border border-gray-200 rounded-lg p-6 space-y-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-gray-900">{fact ? 'Edit Approved Fact' : 'Add Approved Fact'}</h3>
        <button
          type="button"
          onClick={onCancel}
          className="text-gray-400 hover:text-gray-600 text-xl leading-none p-1"
        >
          ×
        </button>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Fact Key *</label>
        <input
          type="text"
          value={form.fact_key}
          onChange={e => handleChange('fact_key', e.target.value.toUpperCase())}
          required
          disabled={!!fact}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent disabled:bg-gray-50"
          placeholder="e.g., FACT-01"
          pattern="^[A-Z0-9]+-[0-9]{2,3}$"
          title="Format: UPPERCASE-NUMBERS (e.g., FACT-01)"
        />
        {!fact && <p className="mt-1 text-xs text-gray-500">Format: PREFIX-NNN (e.g., FACT-01, FACT-12)</p>}
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Statement *</label>
        <textarea
          value={form.statement}
          onChange={e => handleChange('statement', e.target.value)}
          required
          rows={3}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          placeholder="The approved wording"
          maxLength={2000}
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Source Note *</label>
        <input
          type="text"
          value={form.source_note}
          onChange={e => handleChange('source_note', e.target.value)}
          required
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          placeholder="Document, page, date where approved"
          maxLength={500}
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Valid Until</label>
        <input
          type="date"
          value={form.valid_until}
          onChange={e => handleChange('valid_until', e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
        />
        <p className="mt-1 text-xs text-gray-500">Optional. Facts past this date are flagged in lint.</p>
      </div>

      <div className="flex justify-end gap-3 pt-4 border-t border-gray-200">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50"
        >
          Cancel
        </button>
        <button
          type="submit"
          className="px-4 py-2 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary-dark focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
        >
          {fact ? 'Save Changes' : 'Create Fact'}
        </button>
      </div>
    </form>
  );
}

function LintPanel({
  kitId: _kitId,
  isDraft,
  lintResult,
  isLinting,
  onRunLint,
}: {
  kitId: string;
  isDraft: boolean;
  lintResult: KitLintResponse | null;
  isLinting: boolean;
  onRunLint: () => Promise<void>;
}) {
  if (!isDraft) return null;

  const hasErrors = lintResult && lintResult.issues.some(i => i.severity === 'error');
  const hasWarnings = lintResult && lintResult.issues.some(i => i.severity === 'warning');

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-gray-900">Kit Lint</h3>
        <button
          onClick={onRunLint}
          disabled={isLinting}
          className="px-4 py-2 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary-dark focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isLinting ? 'Running...' : 'Run Lint'}
        </button>
      </div>

      {lintResult && (
        <div className="space-y-4">
          <div className={`p-4 rounded-lg ${hasErrors ? 'bg-red-50 border border-red-200' : hasWarnings ? 'bg-yellow-50 border border-yellow-200' : 'bg-green-50 border border-green-200'}`}>
            <div className="flex items-center gap-3">
              <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${hasErrors ? 'bg-red-100 text-red-800' : hasWarnings ? 'bg-yellow-100 text-yellow-800' : 'bg-green-100 text-green-800'}`}>
                {hasErrors ? 'Blocking Errors' : hasWarnings ? 'Warnings Only' : 'All Checks Passed'}
              </span>
              <span className="text-sm text-gray-500">
                {lintResult.issues.filter(i => i.severity === 'error').length} errors, {lintResult.issues.filter(i => i.severity === 'warning').length} warnings
              </span>
            </div>
          </div>

          {lintResult.issues.length > 0 && (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {lintResult.issues.map((issue, idx) => (
                <div
                  key={idx}
                  className={`p-3 rounded-lg border ${issue.severity === 'error' ? 'bg-red-50 border-red-200' : 'bg-yellow-50 border-yellow-200'}`}
                >
                  <div className="flex items-start gap-3">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${issue.severity === 'error' ? 'bg-red-100 text-red-800' : 'bg-yellow-100 text-yellow-800'}`}>
                      {issue.severity.toUpperCase()}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900">{issue.message}</p>
                      {issue.ref_key && (
                        <p className="text-xs text-gray-500 mt-1">Ref: {issue.ref_key} • Code: {issue.code}</p>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="p-3 bg-gray-50 rounded-lg">
            <h4 className="font-medium text-gray-900 mb-2">Statistics</h4>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-sm">
              <div><span className="text-gray-500">Rules:</span> <span className="font-medium ml-1">{lintResult.stats.rules}</span></div>
              <div><span className="text-gray-500">Facts:</span> <span className="font-medium ml-1">{lintResult.stats.facts}</span></div>
              <div><span className="text-gray-500">LLM Rules:</span> <span className="font-medium ml-1">{lintResult.stats.llm_rules}</span></div>
              <div><span className="text-gray-500">Deterministic:</span> <span className="font-medium ml-1">{lintResult.stats.deterministic_rules}</span></div>
              <div><span className="text-gray-500">Prompt Est.:</span> <span className="font-medium ml-1">{lintResult.stats.prompt_chars_estimate.toLocaleString()} chars</span></div>
              <div><span className="text-gray-500">Prompt Cap:</span> <span className="font-medium ml-1">{lintResult.stats.prompt_chars_cap.toLocaleString()} chars</span></div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ActivationPanel({
  kit: _kit,
  isDraft,
  lintResult,
  lintRevision,
  currentDraftRevision,
  pendingMutations,
  isActivating,
  onActivate,
}: {
  kit: BrandKit;
  isDraft: boolean;
  lintResult: KitLintResponse | null;
  lintRevision: number;
  currentDraftRevision: number;
  pendingMutations: number;
  isActivating: boolean;
  onActivate: () => void | Promise<void>;
}) {
  if (!isDraft) return null;

  const lintMatchesRevision = lintResult !== null && lintRevision === currentDraftRevision;
  const hasSuccessfulLint = lintMatchesRevision && lintResult.ok === true;
  const noPendingMutations = pendingMutations === 0;
  const canActivate = hasSuccessfulLint && noPendingMutations;

  let blockReason: string | null = null;
  if (lintResult === null) {
    blockReason = 'Run lint to check for issues before activating.';
  } else if (!lintMatchesRevision) {
    blockReason = 'Kit has changed since lint completed. Re-run lint.';
  } else if (!lintResult.ok) {
    blockReason = 'Resolve all blocking errors before activation.';
  } else if (!noPendingMutations) {
    blockReason = 'A rule or fact change is in progress. Wait for it to complete.';
  }

  const lintStatus = lintResult
    ? lintMatchesRevision
      ? lintResult.ok
        ? 'Ready to activate'
        : 'Fix blocking errors first'
      : 'Kit changed since lint — re-run lint'
    : 'Run lint first';

  const lintStatusColor = lintResult
    ? lintMatchesRevision
      ? lintResult.ok
        ? 'text-green-600'
        : 'text-red-600'
      : 'text-orange-600'
    : 'text-gray-500';

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-4">
      <h3 className="font-semibold text-gray-900">Activate Kit</h3>
      <p className="text-sm text-gray-600">
        This will make this kit the active standard for your organization. The current active kit (if any) will be archived.
      </p>

      <div className="p-4 bg-gray-50 rounded-lg">
        <p className="text-sm font-medium text-gray-900">Lint Status</p>
        <p className={`text-sm ${lintStatusColor} mt-1`}>{lintStatus}</p>
        {blockReason && (
          <p className="text-xs text-gray-500 mt-1">{blockReason}</p>
        )}
      </div>

      <button
        onClick={onActivate}
        disabled={!canActivate || isActivating}
        className={`w-full py-2.5 px-4 rounded-lg font-medium text-white transition-colors ${
          canActivate ? 'bg-primary hover:bg-primary-dark' : 'bg-gray-300 text-gray-500 cursor-not-allowed'
        } ${isActivating ? 'opacity-75' : ''}`}
      >
        {isActivating ? 'Activating...' : 'Activate Kit'}
      </button>

      {!canActivate && blockReason && (
        <p className="text-xs text-gray-500 text-center">{blockReason}</p>
      )}
    </div>
  );
}

/** Kit detail page with full editor capabilities. */
export function KitDetail() {
  const { session, isLoading: authLoading } = useAuth();
  const { kitId } = useParams<{ kitId: string }>();
  const navigate = useNavigate();

  const [kit, setKit] = useState<BrandKit | null>(null);
  const [rules, setRules] = useState<Rule[]>([]);
  const [facts, setFacts] = useState<ApprovedFact[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Editing state
  const [editingRuleId, setEditingRuleId] = useState<string | null>(null);
  const [addingRule, setAddingRule] = useState(false);
  const [editingFactId, setEditingFactId] = useState<string | null>(null);
  const [addingFact, setAddingFact] = useState(false);

  // Lint state with revision tracking
  const [lintResult, setLintResult] = useState<KitLintResponse | null>(null);
  const [isLinting, setIsLinting] = useState(false);
  const [lintRevision, setLintRevision] = useState<number>(0);
  const [currentDraftRevision, setCurrentDraftRevision] = useState<number>(0);

  // Pending mutations counter
  const [pendingMutations, setPendingMutations] = useState<number>(0);

  // Activation state
  const [isActivating, setIsActivating] = useState(false);
  const [showActivateConfirm, setShowActivateConfirm] = useState(false);

  // Delete confirmations
  const [deleteConfirm, setDeleteConfirm] = useState<{ type: 'rule' | 'fact'; id: string; key: string } | null>(null);

  // General error
  const [toastError, setToastError] = useState<string | null>(null);

  // Stale request protection for data loading
  const requestIdRef = useRef(0);

  // Stale request protection for lint
  const lintRequestIdRef = useRef(0);

  const invalidateLintAndBumpRevision = useCallback(() => {
    setLintResult(null);
    setCurrentDraftRevision(prev => prev + 1);
  }, []);

  const beginMutation = useCallback(() => {
    invalidateLintAndBumpRevision();
    setPendingMutations(prev => prev + 1);
  }, [invalidateLintAndBumpRevision]);

  const endMutation = useCallback(() => {
    setPendingMutations(prev => Math.max(0, prev - 1));
  }, []);

  const loadData = useCallback(async () => {
    if (!kitId || !session?.currentOrgId) return;

    const currentRequestId = ++requestIdRef.current;
    setIsLoading(true);
    setError(null);

    try {
      const kits = await getBrandKits(session.currentOrgId);
      const currentKit = kits.find(k => k.id === kitId);

      if (!currentKit) {
        throw new Error('Kit not found');
      }

      if (currentRequestId !== requestIdRef.current) return;

      setKit(currentKit);

      const [kitRules, kitFacts] = await Promise.all([
        getKitRules(kitId),
        getKitFacts(kitId),
      ]);

      if (currentRequestId !== requestIdRef.current) return;

      setRules(kitRules);
      setFacts(kitFacts);
      // Invalidate lint and bump draft revision on kit/org change
      setLintResult(null);
      setCurrentDraftRevision(prev => prev + 1);
    } catch (err) {
      if (currentRequestId !== requestIdRef.current) return;
      setError(err instanceof Error ? err.message : 'Failed to load kit');
    } finally {
      if (currentRequestId === requestIdRef.current) {
        setIsLoading(false);
      }
    }
  }, [kitId, session?.currentOrgId]);

  useEffect(() => {
    if (!authLoading && session && kitId) {
      loadData();
    }
  }, [authLoading, session, kitId, loadData]);

  const handleAddRule = async (data: RuleFormData) => {
    if (!kit) return;
    beginMutation();
    try {
      const newRule = await createRule({ kit_id: kit.id, ...data } as CreateRuleInput);
      setRules(prev => [...prev, newRule].sort((a, b) => a.rule_key.localeCompare(b.rule_key)));
      setAddingRule(false);
    } catch (err) {
      setToastError(err instanceof Error ? err.message : 'Failed to create rule');
    } finally {
      endMutation();
    }
  };

  const handleUpdateRule = async (ruleId: string, data: RuleFormData) => {
    beginMutation();
    try {
      const updatedRule = await updateRule(ruleId, data as UpdateRuleInput);
      setRules(prev => prev.map(r => r.id === ruleId ? updatedRule : r));
      setEditingRuleId(null);
    } catch (err) {
      setToastError(err instanceof Error ? err.message : 'Failed to update rule');
    } finally {
      endMutation();
    }
  };

  const handleDeleteRule = async (ruleId: string) => {
    beginMutation();
    try {
      await deleteRule(ruleId);
      setRules(prev => prev.filter(r => r.id !== ruleId));
      setDeleteConfirm(null);
    } catch (err) {
      setToastError(err instanceof Error ? err.message : 'Failed to delete rule');
    } finally {
      endMutation();
    }
  };

  const handleAddFact = async (data: FactFormData) => {
    if (!kit) return;
    beginMutation();
    try {
      const newFact = await createFact({ kit_id: kit.id, ...data });
      setFacts(prev => [...prev, newFact].sort((a, b) => a.fact_key.localeCompare(b.fact_key)));
      setAddingFact(false);
    } catch (err) {
      setToastError(err instanceof Error ? err.message : 'Failed to create fact');
    } finally {
      endMutation();
    }
  };

  const handleUpdateFact = async (factId: string, data: FactFormData) => {
    beginMutation();
    try {
      const updatedFact = await updateFact(factId, data);
      setFacts(prev => prev.map(f => f.id === factId ? updatedFact : f));
      setEditingFactId(null);
    } catch (err) {
      setToastError(err instanceof Error ? err.message : 'Failed to update fact');
    } finally {
      endMutation();
    }
  };

  const handleSaveVisualGuidelines = async (visualGuidelines: VisualGuidelines) => {
    if (!kit) throw new Error('Kit is not available');
    beginMutation();
    try {
      const saved = await updateKitVisualGuidelines(kit.id, visualGuidelines);
      setKit(current => current ? { ...current, visual_guidelines: saved } : current);
      return saved;
    } finally {
      endMutation();
    }
  };

  const handleDeleteFact = async (factId: string) => {
    beginMutation();
    try {
      await deleteFact(factId);
      setFacts(prev => prev.filter(f => f.id !== factId));
      setDeleteConfirm(null);
    } catch (err) {
      setToastError(err instanceof Error ? err.message : 'Failed to delete fact');
    } finally {
      endMutation();
    }
  };

  const handleRunLint = async () => {
    if (!kit) return;
    
    // Prevent lint from starting while mutations are pending
    if (pendingMutations > 0) {
      setToastError('Cannot run lint while a rule or fact change is in progress. Wait for it to complete.');
      return;
    }
    
    const revisionAtStart = currentDraftRevision;
    const requestId = ++lintRequestIdRef.current;
    const kitIdAtStart = kit.id;
    const orgIdAtStart = session?.currentOrgId;
    setIsLinting(true);
    try {
      const result = await lintKit(kitIdAtStart);
      // Only accept lint result if no mutations occurred during lint,
      // the kit/org hasn't changed, and no mutation is pending at completion
      if (requestId === lintRequestIdRef.current &&
          revisionAtStart === currentDraftRevision &&
          kitIdAtStart === kit?.id &&
          orgIdAtStart === session?.currentOrgId &&
          pendingMutations === 0) {
        setLintResult(result);
        setLintRevision(revisionAtStart);
      }
    } catch (err) {
      // Only show error if this is still the current lint request
      if (requestId === lintRequestIdRef.current) {
        if (err instanceof KitLintError) {
          setToastError(`Lint failed: ${err.message} (${err.status})`);
        } else {
          setToastError(err instanceof Error ? err.message : 'Lint failed');
        }
      }
    } finally {
      if (requestId === lintRequestIdRef.current) {
        setIsLinting(false);
      }
    }
  };

  const handleActivate = async () => {
    // Explicitly re-check all gating conditions immediately before activation
    if (!kit) return;
    if (kit.status !== 'draft') return;
    if (lintResult === null) return;
    if (lintRevision !== currentDraftRevision) return;
    if (!lintResult.ok) return;
    if (pendingMutations > 0) return;
    if (isActivating) return;
    
    setIsActivating(true);
    try {
      await activateKit(kit.id);
      // Navigate back to list to show updated statuses
      navigate('/kits');
    } catch (err) {
      setToastError(err instanceof Error ? err.message : 'Failed to activate kit');
    } finally {
      setIsActivating(false);
      setShowActivateConfirm(false);
    }
  };

  const confirmActivate = () => {
    setShowActivateConfirm(true);
  };

  if (authLoading || !session) {
    return <LoadingScreen message="Loading authentication..." />;
  }

  if (isLoading) {
    return <LoadingScreen message="Loading kit details..." />;
  }

  if (error || !kit) {
    return (
      <div className="space-y-8">
        <Link to="/kits" className="text-primary hover:text-primary-dark inline-flex items-center gap-1">
          ← Back to Kits
        </Link>
        <ErrorAlert message={error || 'Kit not found'} onDismiss={() => navigate('/kits')} />
      </div>
    );
  }

  const isDraft = kit.status === 'draft';
  const isActive = kit.status === 'active';

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-4">
          <Link to="/kits" className="text-primary hover:text-primary-dark inline-flex items-center gap-1">
            ← Back
          </Link>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-gray-900">{kit.name}</h1>
              <StatusBadge status={kit.status} />
              {isActive && <span className="px-2 py-0.5 text-xs font-medium bg-primary text-white rounded">Active</span>}
            </div>
            <p className="text-sm text-gray-500 mt-1">
              Version {kit.version} • Created {new Date(kit.created_at).toLocaleDateString()}
              {kit.activated_at && ` • Activated ${new Date(kit.activated_at).toLocaleDateString()}`}
              {kit.source_kit_id && ` • Cloned from v${kit.version - 1}`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={async () => {
              try {
                const result = await cloneKit(kit.id);
                navigate(`/kits/${result.kit_id}`);
              } catch (err) {
                setToastError(err instanceof Error ? err.message : 'Failed to clone kit');
              }
            }}
            className="px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            Clone Kit
          </button>
        </div>
      </div>

      {/* Error toast */}
      {toastError && (
        <ErrorAlert message={toastError} onDismiss={() => setToastError(null)} />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Main content */}
        <div className="lg:col-span-2 space-y-6">
          <VisualGuidelinesEditor
            kitId={kit.id}
            initialValue={kit.visual_guidelines}
            editable={isDraft}
            saving={pendingMutations > 0}
            onSave={handleSaveVisualGuidelines}
          />

          {/* Rules section */}
          <div className="bg-white border border-gray-200 rounded-lg">
            <div className="p-4 border-b border-gray-200 flex items-center justify-between">
              <h2 className="font-semibold text-gray-900 flex items-center gap-2">
                Rules
                <span className="text-sm text-gray-500 font-normal">({rules.length})</span>
              </h2>
              {isDraft && (
                <button
                  onClick={() => setAddingRule(true)}
                  className="px-3 py-1.5 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary-dark"
                >
                  Add Rule
                </button>
              )}
            </div>
            <div className="divide-y divide-gray-200">
              {rules.length === 0 ? (
                <div className="p-8 text-center text-gray-500">
                  {isDraft ? 'No rules yet. Click "Add Rule" to create one.' : 'This kit has no rules.'}
                </div>
              ) : (
                rules.map(rule => (
                  <div key={rule.id} className="p-4 hover:bg-gray-50">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <code className="px-2 py-0.5 bg-gray-100 rounded text-sm font-mono text-gray-700">{rule.rule_key}</code>
                          <span className="px-2 py-0.5 bg-gray-100 rounded text-xs font-medium text-gray-700 capitalize">{rule.category}</span>
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${rule.severity === 'high' ? 'bg-red-100 text-red-800' : rule.severity === 'medium' ? 'bg-yellow-100 text-yellow-800' : 'bg-green-100 text-green-800'}`}>
                            {rule.severity}
                          </span>
                          <span className="px-2 py-0.5 bg-gray-100 rounded text-xs font-medium text-gray-700">
                            {rule.check_kind === 'deterministic' ? 'Deterministic' : 'LLM'}
                          </span>
                          {rule.needs_reviewer && (
                            <span className="px-2 py-0.5 bg-blue-100 text-blue-800 rounded text-xs font-medium">Reviewer</span>
                          )}
                        </div>
                        <h3 className="font-medium text-gray-900">{rule.title}</h3>
                        <p className="text-sm text-gray-600 mt-1 line-clamp-2">{rule.guideline_text}</p>
                        {(rule.example_bad || rule.example_good) && (
                          <div className="mt-2 text-xs text-gray-500">
                            {rule.example_bad && <p>Bad: {rule.example_bad}</p>}
                            {rule.example_good && <p>Good: {rule.example_good}</p>}
                          </div>
                        )}
                      </div>
                      {isDraft && (
                        <div className="flex items-center gap-2 flex-shrink-0">
                          <button
                            onClick={() => setEditingRuleId(rule.id)}
                            className="px-3 py-1 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => setDeleteConfirm({ type: 'rule', id: rule.id, key: rule.rule_key })}
                            className="px-3 py-1 text-sm font-medium text-red-600 border border-red-300 rounded-lg hover:bg-red-50"
                          >
                            Delete
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Rule Editor */}
            {(addingRule || editingRuleId) && (
              <div className="p-4 border-t border-gray-200 bg-gray-50">
                <RuleEditor
                  rule={editingRuleId ? rules.find(r => r.id === editingRuleId) || null : null}
                  onSave={editingRuleId ? data => handleUpdateRule(editingRuleId, data) : handleAddRule}
                  onCancel={() => { setEditingRuleId(null); setAddingRule(false); }}
                  isEditing={!!editingRuleId || addingRule}
                  categories={CATEGORIES}
                  severities={SEVERITIES}
                  checkKinds={CHECK_KINDS}
                />
              </div>
            )}
          </div>

          {/* Approved Facts section */}
          <div className="bg-white border border-gray-200 rounded-lg">
            <div className="p-4 border-b border-gray-200 flex items-center justify-between">
              <h2 className="font-semibold text-gray-900 flex items-center gap-2">
                Approved Facts
                <span className="text-sm text-gray-500 font-normal">({facts.length})</span>
              </h2>
              {isDraft && (
                <button
                  onClick={() => setAddingFact(true)}
                  className="px-3 py-1.5 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary-dark"
                >
                  Add Fact
                </button>
              )}
            </div>
            <div className="divide-y divide-gray-200">
              {facts.length === 0 ? (
                <div className="p-8 text-center text-gray-500">
                  {isDraft ? 'No approved facts yet. Click "Add Fact" to create one.' : 'This kit has no approved facts.'}
                </div>
              ) : (
                facts.map(fact => (
                  <div key={fact.id} className="p-4 hover:bg-gray-50">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <code className="px-2 py-0.5 bg-gray-100 rounded text-sm font-mono text-gray-700">{fact.fact_key}</code>
                          {fact.valid_until && new Date(fact.valid_until) < new Date() && (
                            <span className="px-2 py-0.5 bg-red-100 text-red-800 rounded text-xs font-medium">Expired</span>
                          )}
                        </div>
                        <p className="font-medium text-gray-900">{fact.statement}</p>
                        <p className="text-sm text-gray-500 mt-1">Source: {fact.source_note}</p>
                        {fact.valid_until && (
                          <p className="text-xs text-gray-400 mt-1">Valid until: {new Date(fact.valid_until).toLocaleDateString()}</p>
                        )}
                      </div>
                      {isDraft && (
                        <div className="flex items-center gap-2 flex-shrink-0">
                          <button
                            onClick={() => setEditingFactId(fact.id)}
                            className="px-3 py-1 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => setDeleteConfirm({ type: 'fact', id: fact.id, key: fact.fact_key })}
                            className="px-3 py-1 text-sm font-medium text-red-600 border border-red-300 rounded-lg hover:bg-red-50"
                          >
                            Delete
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Fact Editor */}
            {(addingFact || editingFactId) && (
              <div className="p-4 border-t border-gray-200 bg-gray-50">
                <FactEditor
                  fact={editingFactId ? facts.find(f => f.id === editingFactId) || null : null}
                  onSave={editingFactId ? data => handleUpdateFact(editingFactId, data) : handleAddFact}
                  onCancel={() => { setEditingFactId(null); setAddingFact(false); }}
                  isEditing={!!editingFactId || addingFact}
                />
              </div>
            )}
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          <LintPanel
            kitId={kit.id}
            isDraft={isDraft}
            lintResult={lintResult}
            isLinting={isLinting}
            onRunLint={handleRunLint}
          />

          <ActivationPanel
            kit={kit}
            isDraft={isDraft}
            lintResult={lintResult}
            lintRevision={lintRevision}
            currentDraftRevision={currentDraftRevision}
            pendingMutations={pendingMutations}
            isActivating={isActivating}
            onActivate={confirmActivate}
          />
        </div>
      </div>

      {/* Delete confirmation dialog */}
      <ConfirmDialog
        isOpen={!!deleteConfirm}
        title={`Delete ${deleteConfirm?.type === 'rule' ? 'Rule' : 'Fact'}`}
        message={`Are you sure you want to delete ${deleteConfirm?.type === 'rule' ? 'rule' : 'fact'} "${deleteConfirm?.key}"? This action cannot be undone.`}
        onConfirm={() => {
          if (deleteConfirm) {
            if (deleteConfirm.type === 'rule') handleDeleteRule(deleteConfirm.id);
            else handleDeleteFact(deleteConfirm.id);
          }
        }}
        onCancel={() => setDeleteConfirm(null)}
        confirmText="Delete"
        variant="danger"
      />

      {/* Activation confirmation dialog */}
      <ConfirmDialog
        isOpen={showActivateConfirm}
        title="Activate Kit"
        message={`Activate "${kit.name}" (v${kit.version})? This will make it the active brand kit for your organization. The current active kit will be archived.`}
        onConfirm={handleActivate}
        onCancel={() => setShowActivateConfirm(false)}
        confirmText="Activate"
        variant="primary"
      />
    </div>
  );
}

export default KitDetail;
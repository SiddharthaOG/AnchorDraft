/** Content creation form - allows creator to create new content with active brand kit. */

import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../features/auth/AuthProvider';
import { LoadingScreen } from '../../components/LoadingScreen';
import {
  getActiveKit,
  createContent,
  type BrandKit,
  type Content,
  type CreateContentResult,
} from '../../lib/data';

interface FormData {
  title: string;
  channel: Content['channel'];
  purpose: string;
  body: string;
}

const initialFormData: FormData = {
  title: '',
  channel: 'other',
  purpose: '',
  body: '',
};

const CHANNELS = ['linkedin', 'blog', 'email', 'website', 'other'] as const;

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

/** Content creation page. */
export function ContentCreate() {
  const { session, isLoading: authLoading } = useAuth();
  const navigate = useNavigate();

  const [activeKit, setActiveKit] = useState<BrandKit | null>(null);
  const [isLoadingKit, setIsLoadingKit] = useState(true);
  const [kitError, setKitError] = useState<string | null>(null);

  const [formData, setFormData] = useState<FormData>(initialFormData);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<CreateContentResult | null>(null);

  // Load active kit
  useEffect(() => {
    if (!session?.currentOrgId) return;

    setIsLoadingKit(true);
    setKitError(null);

    getActiveKit(session.currentOrgId)
      .then(kit => {
        setActiveKit(kit);
        setKitError(null);
      })
      .catch(err => {
        setKitError(err instanceof Error ? err.message : 'Failed to load active kit');
      })
      .finally(() => {
        setIsLoadingKit(false);
      });
  }, [session?.currentOrgId]);

  const handleChange = (field: keyof FormData, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    if (submitError) setSubmitError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Validate required fields
    if (!formData.title.trim()) {
      setSubmitError('Title is required');
      return;
    }
    if (!formData.purpose.trim()) {
      setSubmitError('Purpose is required');
      return;
    }
    if (!formData.body.trim()) {
      setSubmitError('Content body is required');
      return;
    }
    if (!activeKit) {
      setSubmitError('No active brand kit available. Please contact your Guideline Owner.');
      return;
    }

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      const result = await createContent(
        session!.currentOrgId!,
        formData.title.trim(),
        formData.channel,
        formData.purpose.trim(),
        formData.body.trim()
      );

      setSubmitSuccess(result);
      // Navigate to content detail after successful creation
      navigate(`/contents/${result.content_id}`);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to create content');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (authLoading || !session) {
    return <LoadingScreen message="Loading authentication..." />;
  }

  if (isLoadingKit) {
    return <LoadingScreen message="Loading active brand kit..." />;
  }

  if (kitError) {
    return (
      <div className="space-y-8">
        <ErrorAlert message={kitError} onDismiss={() => {}} />
      </div>
    );
  }

  if (!activeKit) {
    return (
      <div className="space-y-8">
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6">
          <h3 className="font-semibold text-yellow-800">No Active Brand Kit</h3>
          <p className="text-yellow-700 text-sm mt-1">
            You need an active brand kit to create content. Please contact your Guideline Owner to activate a kit.
          </p>
        </div>
      </div>
    );
  }

  if (submitSuccess) {
    return (
      <div className="space-y-8">
        <div className="bg-green-50 border border-green-200 rounded-lg p-6">
          <h3 className="font-semibold text-green-800">Content Created Successfully</h3>
          <p className="text-green-700 text-sm mt-1">Redirecting to content detail...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Create New Content</h1>
        <p className="text-gray-600 mt-1">Create a new draft using the active brand kit.</p>
      </div>

      {/* Active Kit Info */}
      <div className="bg-white border border-gray-200 rounded-lg p-6">
        <h3 className="font-semibold text-gray-900 mb-4">Active Brand Kit</h3>
        <div className="flex items-center gap-4">
          <div>
            <p className="font-medium text-gray-900">{activeKit.name}</p>
            <p className="text-sm text-gray-500">Version {activeKit.version}</p>
          </div>
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
            Active
          </span>
        </div>
      </div>

      {/* Error toast */}
      {submitError && (
        <ErrorAlert message={submitError} onDismiss={() => setSubmitError(null)} />
      )}

      {/* Content Form */}
      <form onSubmit={handleSubmit} className="bg-white border border-gray-200 rounded-lg p-6 space-y-6">
        <div>
          <label htmlFor="title" className="block text-sm font-medium text-gray-700 mb-1">
            Title *
          </label>
          <input
            id="title"
            type="text"
            value={formData.title}
            onChange={e => handleChange('title', e.target.value)}
            required
            maxLength={200}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            placeholder="Enter content title"
          />
        </div>

        <div>
          <label htmlFor="channel" className="block text-sm font-medium text-gray-700 mb-1">
            Channel *
          </label>
          <select
            id="channel"
            value={formData.channel}
            onChange={e => handleChange('channel', e.target.value)}
            required
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          >
            {CHANNELS.map(c => (
              <option key={c} value={c}>
                {c.charAt(0).toUpperCase() + c.slice(1)}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="purpose" className="block text-sm font-medium text-gray-700 mb-1">
            Purpose *
          </label>
          <textarea
            id="purpose"
            value={formData.purpose}
            onChange={e => handleChange('purpose', e.target.value)}
            required
            maxLength={1000}
            rows={3}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            placeholder="Describe the intent and goal of this content"
          />
          <p className="mt-1 text-xs text-gray-500">Explain the purpose and goal of this content. This helps the review engine understand context.</p>
        </div>

        <div>
          <label htmlFor="body" className="block text-sm font-medium text-gray-700 mb-1">
            Content Body *
          </label>
          <textarea
            id="body"
            value={formData.body}
            onChange={e => handleChange('body', e.target.value)}
            required
            maxLength={20000}
            rows={15}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent font-mono text-sm"
            placeholder="Write your content here..."
          />
          <p className="mt-1 text-xs text-gray-500">Maximum 20,000 characters.</p>
        </div>

        <div className="flex justify-end gap-3 pt-4 border-t border-gray-200">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={isSubmitting}
            className="px-4 py-2 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary-dark focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSubmitting ? 'Creating...' : 'Create Content'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default ContentCreate;
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

afterEach(cleanup);

const mocks = vi.hoisted(() => ({
  getGuidelineGapAnalytics: vi.fn(),
  createGuidelineSuggestionPreview: vi.fn(),
  confirmGuidelineSuggestionPreview: vi.fn(),
  acceptGuidelineSuggestion: vi.fn(),
  rejectGuidelineSuggestion: vi.fn(),
  hasAnyRole: vi.fn(),
}));

vi.mock('../../lib/data', () => ({
  getGuidelineGapAnalytics: mocks.getGuidelineGapAnalytics,
  createGuidelineSuggestionPreview: mocks.createGuidelineSuggestionPreview,
  confirmGuidelineSuggestionPreview: mocks.confirmGuidelineSuggestionPreview,
  acceptGuidelineSuggestion: mocks.acceptGuidelineSuggestion,
  rejectGuidelineSuggestion: mocks.rejectGuidelineSuggestion,
}));

vi.mock('../auth/AuthProvider', () => ({
  useAuth: () => ({ hasAnyRole: mocks.hasAnyRole }),
}));

import { GuidelineGapPanel } from './GuidelineGapPanel';

const analytics = {
  kit: { id: 'kit-1', version: 4, name: 'Example Kit' },
  rules: [{
    rule_key: 'CLAIM-01',
    category: 'claim',
    title: 'Substantiate claims',
    guideline_text: 'Avoid unsupported claims.',
    decided: 5,
    dismissed: 4,
    acted_on: 1,
    dismissal_rate: 0.8,
    source_versions: [2, 3, 4],
    is_gap: true,
    reason_clusters: [],
    suggestion: null,
  }],
  gaps: [{
    rule_key: 'CLAIM-01',
    category: 'claim',
    title: 'Substantiate claims',
    guideline_text: 'Avoid unsupported claims.',
    decided: 5,
    dismissed: 4,
    acted_on: 1,
    dismissal_rate: 0.8,
    source_versions: [2, 3, 4],
    is_gap: true,
    reason_clusters: [{
      theme: 'too / vague',
      count: 4,
      examples: ['Too vague', 'The wording is too vague'],
      qualifies: true,
    }],
    suggestion: null,
  }],
};

describe('GuidelineGapPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.hasAnyRole.mockReturnValue(true);
    mocks.getGuidelineGapAnalytics.mockResolvedValue(analytics);
    mocks.createGuidelineSuggestionPreview.mockResolvedValue({
      preview_id: 'preview-1',
      confirmation_token: 'token-123456789012345678901234567890',
      expires_at: '2026-11-12T12:00:00Z',
      payload_sha256: 'a'.repeat(64),
      system_instruction: 'Edit the guideline.',
      user_content: 'Current: [CUSTOM_TERM-12345678]',
      redaction_summary: {
        total_matches: 1,
        by_type: { custom_term: 1 },
        original_chars: 40,
        redacted_chars: 35,
        policy_version: 2,
      },
    });
    mocks.confirmGuidelineSuggestionPreview.mockResolvedValue({
      id: 'suggestion-1',
      status: 'pending',
      rule_key: 'CLAIM-01',
      suggested_text: 'Substantiate performance claims with approved evidence.',
      explanation: 'Clarifies what evidence is required.',
      source_kit_version: 4,
      created_at: '2026-11-12T11:00:00Z',
      model: 'fake-model',
    });
    mocks.acceptGuidelineSuggestion.mockResolvedValue({
      status: 'accepted',
      kit_id: 'kit-5',
      version: 5,
    });
  });

  it('shows the exact redacted payload before confirming a suggestion', async () => {
    const pendingAnalytics = {
      ...analytics,
      gaps: [{
        ...analytics.gaps[0],
        suggestion: {
          id: 'suggestion-1',
          rule_key: 'CLAIM-01',
          status: 'pending',
          suggested_text: 'Substantiate claims with approved evidence.',
          explanation: 'Clarifies the evidence requirement.',
          source_kit_version: 4,
          created_at: '2026-11-12T11:00:00Z',
          accepted_kit_id: null,
        },
      }],
    };
    mocks.getGuidelineGapAnalytics.mockResolvedValueOnce(analytics).mockResolvedValue(pendingAnalytics);

    render(<GuidelineGapPanel />);

    expect(await screen.findByText('Dismissal reason groups')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Preview wording suggestion' }));

    expect(await screen.findByText('Review exactly what will leave AnchorDraft')).toBeInTheDocument();
    expect(screen.getByText('Current: [CUSTOM_TERM-12345678]')).toBeInTheDocument();
    expect(mocks.confirmGuidelineSuggestionPreview).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Confirm and generate suggestion' }));
    await waitFor(() => expect(mocks.confirmGuidelineSuggestionPreview).toHaveBeenCalledWith('preview-1', 'token-123456789012345678901234567890'));
    expect(await screen.findByText('Substantiate claims with approved evidence.')).toBeInTheDocument();
  });

  it('accepts a proposal through the human decision action', async () => {
    const pendingAnalytics = {
      ...analytics,
      gaps: [{
        ...analytics.gaps[0],
        suggestion: {
          id: 'suggestion-1',
          rule_key: 'CLAIM-01',
          status: 'pending',
          suggested_text: 'Substantiate claims with approved evidence.',
          explanation: 'Clarifies the evidence requirement.',
          source_kit_version: 4,
          created_at: '2026-11-12T11:00:00Z',
          accepted_kit_id: null,
        },
      }],
    };
    mocks.getGuidelineGapAnalytics.mockResolvedValue(pendingAnalytics);

    render(<GuidelineGapPanel />);

    fireEvent.click(await screen.findByRole('button', { name: 'Accept and create new kit version' }));
    await waitFor(() => expect(mocks.acceptGuidelineSuggestion).toHaveBeenCalledWith('suggestion-1'));
    expect(await screen.findByText('Accepted. Brand kit version 5 is now active.')).toBeInTheDocument();
  });

  it('shows reviewer decision coverage and distinguishes insufficient evidence', async () => {
    mocks.getGuidelineGapAnalytics.mockResolvedValue({
      ...analytics,
      rules: [
        ...analytics.rules,
        {
          rule_key: 'TONE-01',
          category: 'tone',
          title: 'Use a consistent tone',
          guideline_text: 'Use a consistent tone.',
          decided: 2,
          dismissed: 1,
          acted_on: 1,
          dismissal_rate: 0.5,
          source_versions: [4],
          is_gap: false,
          reason_clusters: [],
          suggestion: null,
        },
      ],
    });

    render(<GuidelineGapPanel />);

    expect(await screen.findByText('Reviewer decision coverage')).toBeInTheDocument();
    expect(screen.getByText(/2\s*\/\s*2/)).toBeInTheDocument();
    expect(screen.getByText('Insufficient evidence')).toBeInTheDocument();
    expect(screen.getByText('Potential gap')).toBeInTheDocument();
  });

  it('rejects a pending suggestion with the optional reviewer reason', async () => {
    const pendingAnalytics = {
      ...analytics,
      gaps: [{
        ...analytics.gaps[0],
        suggestion: {
          id: 'suggestion-1',
          rule_key: 'CLAIM-01',
          status: 'pending',
          suggested_text: 'Substantiate claims with approved evidence.',
          explanation: 'Clarifies the evidence requirement.',
          source_kit_version: 4,
          created_at: '2026-11-12T11:00:00Z',
          accepted_kit_id: null,
        },
      }],
    };
    mocks.getGuidelineGapAnalytics.mockResolvedValue(pendingAnalytics);

    render(<GuidelineGapPanel />);

    fireEvent.change(await screen.findByLabelText('Optional rejection reason for CLAIM-01'), {
      target: { value: 'This changes the intended meaning.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Reject' }));

    await waitFor(() => expect(mocks.rejectGuidelineSuggestion).toHaveBeenCalledWith(
      'suggestion-1',
      'This changes the intended meaning.',
    ));
    expect(await screen.findByText('Suggestion rejected and recorded.')).toBeInTheDocument();
  });

  it('does not render for reviewers', () => {
    mocks.hasAnyRole.mockReturnValue(false);
    const { container } = render(<GuidelineGapPanel />);
    expect(container.firstChild).toBeNull();
  });
});

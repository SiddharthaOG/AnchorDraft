import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ConfidentialitySettings } from './ConfidentialitySettings';

const { getPolicy, updatePolicy } = vi.hoisted(() => ({
  getPolicy: vi.fn(),
  updatePolicy: vi.fn(),
}));

vi.mock('../../lib/confidentiality', () => ({
  getConfidentialityPolicy: getPolicy,
  updateConfidentialityPolicy: updatePolicy,
}));

const initial = {
  org_id: 'org-1', version: 1, enabled: true, custom_terms: ['ORCHID-VAULT-ALPHA'],
  redact_emails: true, redact_phones: true, redact_api_keys: true, redact_jwts: true, redact_credit_cards: true,
};

describe('ConfidentialitySettings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getPolicy.mockResolvedValue(initial);
    updatePolicy.mockImplementation(async value => ({ ...initial, ...value, version: 2 }));
  });
  afterEach(cleanup);

  it('loads policy and saves owner-defined terms', async () => {
    render(<ConfidentialitySettings />);
    expect(await screen.findByText('Confidentiality controls')).toBeInTheDocument();
    const terms = screen.getByLabelText('Organisation-specific terms');
    fireEvent.change(terms, { target: { value: 'ORCHID-VAULT-ALPHA\nNEVER-SEND-ORIGINAL-TEXT-7F92' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save policy' }));
    await waitFor(() => expect(updatePolicy).toHaveBeenCalledWith({
      enabled: true,
      custom_terms: ['ORCHID-VAULT-ALPHA', 'NEVER-SEND-ORIGINAL-TEXT-7F92'],
      redact_emails: true,
      redact_phones: true,
      redact_api_keys: true,
      redact_jwts: true,
      redact_credit_cards: true,
    }));
    expect(updatePolicy.mock.calls[0][0]).not.toHaveProperty('org_id');
    expect(updatePolicy.mock.calls[0][0]).not.toHaveProperty('version');
    expect(await screen.findByText(/Saved as policy version 2/)).toBeInTheDocument();
  });

  it('shows API errors without discarding the loaded settings', async () => {
    updatePolicy.mockRejectedValueOnce(new Error('Forbidden'));
    render(<ConfidentialitySettings />);
    fireEvent.click(await screen.findByRole('button', { name: 'Save policy' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Forbidden');
  });
});

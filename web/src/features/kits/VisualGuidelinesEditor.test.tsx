import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { VisualGuidelinesEditor } from './VisualGuidelinesEditor';

afterEach(cleanup);

const initialValue = {
  palette: {
    colors: [{ name: 'Primary', hex: '#123456' }],
    tolerance: 10,
    allow_neutrals: true,
  },
};

describe('VisualGuidelinesEditor', () => {
  it('saves structured palette settings', async () => {
    const saved = {
      palette: {
        colors: [{ name: 'Primary Brand', hex: '#234567' }],
        tolerance: 12,
        allow_neutrals: false,
      },
    };
    const onSave = vi.fn().mockResolvedValue(saved);
    render(
      <VisualGuidelinesEditor
        kitId="kit-draft-1"
        initialValue={initialValue}
        editable
        saving={false}
        onSave={onSave}
      />,
    );

    fireEvent.change(screen.getByLabelText('Palette color name 1'), {
      target: { value: 'Primary Brand' },
    });
    fireEvent.change(screen.getByLabelText('Palette color hex 1'), {
      target: { value: '#234567' },
    });
    fireEvent.change(screen.getByLabelText('Palette tolerance'), {
      target: { value: '12' },
    });
    fireEvent.click(screen.getByLabelText('Allow neutral colors'));
    fireEvent.click(screen.getByRole('button', { name: 'Save visual guidelines' }));

    await waitFor(() => expect(onSave).toHaveBeenCalledWith(saved));
    expect(await screen.findByRole('status')).toHaveTextContent('Run kit lint again before activation.');
  });

  it('builds logo guidance from description and approved variants', async () => {
    const onSave = vi.fn().mockResolvedValue({
      logo: {
        required: true,
        description: 'White wordmark with leaf icon',
        variants: ['primary', 'monochrome'],
        clear_space_ratio: 0.1,
        min_size_px: 32,
      },
    });
    render(
      <VisualGuidelinesEditor
        kitId="kit-draft-1"
        initialValue={{}}
        editable
        saving={false}
        onSave={onSave}
      />,
    );

    fireEvent.click(screen.getByLabelText('Check logo usage'));
    fireEvent.change(screen.getByLabelText('Logo description'), {
      target: { value: 'White wordmark with leaf icon' },
    });
    fireEvent.change(screen.getByLabelText('Approved logo variants'), {
      target: { value: 'primary, monochrome' },
    });
    fireEvent.click(screen.getByLabelText('Logo must appear in every reviewed asset'));
    fireEvent.click(screen.getByRole('button', { name: 'Save visual guidelines' }));

    await waitFor(() => expect(onSave).toHaveBeenCalledWith({
      logo: {
        required: true,
        description: 'White wordmark with leaf icon',
        variants: ['primary', 'monochrome'],
        clear_space_ratio: 0.1,
        min_size_px: 32,
      },
    }));
  });

  it('saves contrast thresholds and ignored backgrounds', async () => {
    const saved = {
      contrast: {
        min_ratio: 7,
        level: 'AAA' as const,
        ignore_backgrounds: ['#FFFFFF'],
      },
    };
    const onSave = vi.fn().mockResolvedValue(saved);
    render(
      <VisualGuidelinesEditor
        kitId="kit-draft-1"
        initialValue={{}}
        editable
        saving={false}
        onSave={onSave}
      />,
    );

    fireEvent.click(screen.getByLabelText('Check text contrast'));
    fireEvent.change(screen.getByLabelText('Minimum contrast ratio'), {
      target: { value: '7' },
    });
    fireEvent.change(screen.getByLabelText('Contrast standard'), {
      target: { value: 'AAA' },
    });
    fireEvent.change(screen.getByLabelText('Ignored contrast backgrounds'), {
      target: { value: '#FFFFFF' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save visual guidelines' }));

    await waitFor(() => expect(onSave).toHaveBeenCalledWith(saved));
  });

  it('shows server validation errors without losing the form', async () => {
    const onSave = vi.fn().mockRejectedValue(new Error('Palette hex values must be valid colors.'));
    render(
      <VisualGuidelinesEditor
        kitId="kit-draft-1"
        initialValue={initialValue}
        editable
        saving={false}
        onSave={onSave}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Save visual guidelines' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Palette hex values must be valid colors.');
    expect(screen.getByLabelText('Palette color hex 1')).toHaveValue('#123456');
  });

  it('renders active kit settings as read-only', () => {
    render(
      <VisualGuidelinesEditor
        kitId="kit-active-1"
        initialValue={initialValue}
        editable={false}
        saving={false}
        onSave={vi.fn()}
      />,
    );

    expect(screen.getByLabelText('Check brand palette')).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Save visual guidelines' })).not.toBeInTheDocument();
    expect(screen.getByText(/Clone it to configure visual guidelines/)).toBeInTheDocument();
  });

  it('disables all editing while a kit mutation is in progress', () => {
    render(
      <VisualGuidelinesEditor
        kitId="kit-draft-1"
        initialValue={initialValue}
        editable
        saving
        onSave={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled();
    expect(screen.getByLabelText('Check brand palette')).toBeDisabled();
  });
});

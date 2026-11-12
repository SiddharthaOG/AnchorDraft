import { useEffect, useState } from 'react';
import type { VisualGuidelines } from '../../lib/data';

interface VisualGuidelinesEditorProps {
  kitId: string;
  initialValue: VisualGuidelines | null | undefined;
  editable: boolean;
  saving: boolean;
  onSave: (value: VisualGuidelines) => Promise<VisualGuidelines>;
}

interface PaletteColorDraft {
  name: string;
  hex: string;
}

interface GuidelineDraft {
  logoEnabled: boolean;
  logoRequired: boolean;
  logoDescription: string;
  logoVariants: string;
  clearSpaceRatio: string;
  minSizePx: string;
  paletteEnabled: boolean;
  paletteColors: PaletteColorDraft[];
  paletteTolerance: string;
  allowNeutrals: boolean;
  contrastEnabled: boolean;
  minRatio: string;
  contrastLevel: 'AA' | 'AAA';
  ignoreBackgrounds: string;
}

function toDraft(value: VisualGuidelines | null | undefined): GuidelineDraft {
  return {
    logoEnabled: Boolean(value?.logo),
    logoRequired: value?.logo?.required ?? false,
    logoDescription: value?.logo?.description ?? '',
    logoVariants: value?.logo?.variants?.join(', ') ?? '',
    clearSpaceRatio: String(value?.logo?.clear_space_ratio ?? 0.1),
    minSizePx: String(value?.logo?.min_size_px ?? 32),
    paletteEnabled: Boolean(value?.palette),
    paletteColors: value?.palette?.colors?.length
      ? value.palette.colors.map((color) => ({ ...color }))
      : [{ name: 'Primary', hex: '#123456' }],
    paletteTolerance: String(value?.palette?.tolerance ?? 10),
    allowNeutrals: value?.palette?.allow_neutrals ?? true,
    contrastEnabled: Boolean(value?.contrast),
    minRatio: String(value?.contrast?.min_ratio ?? 4.5),
    contrastLevel: value?.contrast?.level ?? 'AA',
    ignoreBackgrounds: value?.contrast?.ignore_backgrounds?.join(', ') ?? '#FFFFFF, #000000',
  };
}

export function VisualGuidelinesEditor({
  kitId,
  initialValue,
  editable,
  saving,
  onSave,
}: VisualGuidelinesEditorProps) {
  const [draft, setDraft] = useState(() => toDraft(initialValue));
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    setDraft(toDraft(initialValue));
    setError(null);
    setNotice(null);
  }, [kitId, initialValue]);

  const update = <K extends keyof GuidelineDraft>(key: K, value: GuidelineDraft[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };

  const handleSave = async () => {
    setError(null);
    setNotice(null);

    const guidelines: VisualGuidelines = {};
    if (draft.logoEnabled) {
      guidelines.logo = {
        required: draft.logoRequired,
        description: draft.logoDescription.trim() || undefined,
        variants: draft.logoVariants.split(',').map((value) => value.trim()).filter(Boolean),
        clear_space_ratio: Number(draft.clearSpaceRatio),
        min_size_px: Number(draft.minSizePx),
      };
    }
    if (draft.paletteEnabled) {
      guidelines.palette = {
        colors: draft.paletteColors.map((color) => ({
          name: color.name.trim(),
          hex: color.hex.trim(),
        })),
        tolerance: Number(draft.paletteTolerance),
        allow_neutrals: draft.allowNeutrals,
      };
    }
    if (draft.contrastEnabled) {
      guidelines.contrast = {
        min_ratio: Number(draft.minRatio),
        level: draft.contrastLevel,
        ignore_backgrounds: draft.ignoreBackgrounds
          .split(',')
          .map((value) => value.trim())
          .filter(Boolean),
      };
    }

    try {
      const saved = await onSave(guidelines);
      setDraft(toDraft(saved));
      setNotice('Visual guidelines saved. Run kit lint again before activation.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to save visual guidelines.');
    }
  };

  const disabled = !editable || saving;

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-5 space-y-5" aria-labelledby="visual-guidelines-heading">
      <div>
        <h2 id="visual-guidelines-heading" className="font-semibold text-gray-900">Visual brand guidelines</h2>
        <p className="mt-1 text-sm text-gray-600">
          Configure the logo, brand palette, and contrast checks used during image review.
        </p>
      </div>

      <fieldset disabled={disabled} className="space-y-5 disabled:opacity-70">
        <div className="rounded-lg border border-gray-200 p-4 space-y-3">
          <label className="flex items-center gap-2 text-sm font-semibold text-gray-900">
            <input
              type="checkbox"
              checked={draft.logoEnabled}
              onChange={(event) => update('logoEnabled', event.target.checked)}
            />
            Check logo usage
          </label>
          {draft.logoEnabled && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <label className="md:col-span-2 block text-sm text-gray-700">
                Logo description
                <input
                  aria-label="Logo description"
                  value={draft.logoDescription}
                  onChange={(event) => update('logoDescription', event.target.value)}
                  maxLength={500}
                  placeholder="Describe the mark, wordmark, colors, and distinctive details"
                  className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                />
              </label>
              <label className="md:col-span-2 block text-sm text-gray-700">
                Approved variants
                <input
                  aria-label="Approved logo variants"
                  value={draft.logoVariants}
                  onChange={(event) => update('logoVariants', event.target.value)}
                  placeholder="Primary, monochrome, reversed"
                  className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                />
                <span className="mt-1 block text-xs text-gray-500">Separate variants with commas.</span>
              </label>
              <label className="flex items-center gap-2 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={draft.logoRequired}
                  onChange={(event) => update('logoRequired', event.target.checked)}
                />
                Logo must appear in every reviewed asset
              </label>
              <label className="block text-sm text-gray-700">
                Clear-space ratio
                <input
                  aria-label="Clear-space ratio"
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  value={draft.clearSpaceRatio}
                  onChange={(event) => update('clearSpaceRatio', event.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                />
              </label>
              <label className="block text-sm text-gray-700">
                Minimum logo size (px)
                <input
                  aria-label="Minimum logo size"
                  type="number"
                  min="1"
                  max="4096"
                  value={draft.minSizePx}
                  onChange={(event) => update('minSizePx', event.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                />
              </label>
              <p className="md:col-span-2 text-xs text-gray-500">
                Logo presence, variant, and placement are assessed by the vision model against the submitted creative.
              </p>
            </div>
          )}
        </div>

        <div className="rounded-lg border border-gray-200 p-4 space-y-3">
          <label className="flex items-center gap-2 text-sm font-semibold text-gray-900">
            <input
              type="checkbox"
              checked={draft.paletteEnabled}
              onChange={(event) => update('paletteEnabled', event.target.checked)}
            />
            Check brand palette
          </label>
          {draft.paletteEnabled && (
            <div className="space-y-3">
              <div className="space-y-2">
                {draft.paletteColors.map((color, index) => (
                  <div key={index} className="grid grid-cols-[1fr_130px_auto] gap-2 items-end">
                    <label className="block text-xs text-gray-600">
                      Color name
                      <input
                        aria-label={'Palette color name ' + (index + 1)}
                        value={color.name}
                        onChange={(event) => update('paletteColors', draft.paletteColors.map((item, itemIndex) => itemIndex === index ? { ...item, name: event.target.value } : item))}
                        maxLength={40}
                        className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                      />
                    </label>
                    <label className="block text-xs text-gray-600">
                      Hex value
                      <input
                        aria-label={'Palette color hex ' + (index + 1)}
                        value={color.hex}
                        onChange={(event) => update('paletteColors', draft.paletteColors.map((item, itemIndex) => itemIndex === index ? { ...item, hex: event.target.value } : item))}
                        placeholder="#123456"
                        className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono"
                      />
                    </label>
                    <button
                      type="button"
                      onClick={() => update('paletteColors', draft.paletteColors.filter((_, itemIndex) => itemIndex !== index))}
                      disabled={draft.paletteColors.length === 1}
                      aria-label={'Remove palette color ' + (index + 1)}
                      className="rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-600 disabled:opacity-40"
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
              <button
                type="button"
                onClick={() => update('paletteColors', [...draft.paletteColors, { name: '', hex: '' }])}
                disabled={draft.paletteColors.length >= 12}
                className="text-sm font-medium text-primary disabled:opacity-40"
              >
                Add brand color
              </button>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <label className="block text-sm text-gray-700">
                  Palette tolerance (0–100)
                  <input
                    aria-label="Palette tolerance"
                    type="number"
                    min="0"
                    max="100"
                    value={draft.paletteTolerance}
                    onChange={(event) => update('paletteTolerance', event.target.value)}
                    className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                  />
                </label>
                <label className="flex items-center gap-2 self-end pb-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={draft.allowNeutrals}
                    onChange={(event) => update('allowNeutrals', event.target.checked)}
                  />
                  Allow neutral colors
                </label>
              </div>
            </div>
          )}
        </div>

        <div className="rounded-lg border border-gray-200 p-4 space-y-3">
          <label className="flex items-center gap-2 text-sm font-semibold text-gray-900">
            <input
              type="checkbox"
              checked={draft.contrastEnabled}
              onChange={(event) => update('contrastEnabled', event.target.checked)}
            />
            Check text contrast
          </label>
          {draft.contrastEnabled && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <label className="block text-sm text-gray-700">
                Minimum contrast ratio
                <input
                  aria-label="Minimum contrast ratio"
                  type="number"
                  min="1"
                  max="21"
                  step="0.1"
                  value={draft.minRatio}
                  onChange={(event) => update('minRatio', event.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                />
              </label>
              <label className="block text-sm text-gray-700">
                Standard
                <select
                  aria-label="Contrast standard"
                  value={draft.contrastLevel}
                  onChange={(event) => update('contrastLevel', event.target.value as 'AA' | 'AAA')}
                  className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                >
                  <option value="AA">WCAG AA</option>
                  <option value="AAA">WCAG AAA</option>
                </select>
              </label>
              <label className="md:col-span-2 block text-sm text-gray-700">
                Background colors to ignore
                <input
                  aria-label="Ignored contrast backgrounds"
                  value={draft.ignoreBackgrounds}
                  onChange={(event) => update('ignoreBackgrounds', event.target.value)}
                  placeholder="#FFFFFF, #000000"
                  className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono"
                />
                <span className="mt-1 block text-xs text-gray-500">Separate hex colors with commas.</span>
              </label>
            </div>
          )}
        </div>
      </fieldset>

      {!editable && (
        <p className="text-xs text-gray-500">This kit version is immutable. Clone it to configure visual guidelines on a new draft.</p>
      )}

      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      {notice && <p role="status" className="text-sm text-green-700">{notice}</p>}

      {editable && (
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => void handleSave()}
            disabled={saving}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-dark disabled:cursor-wait disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Save visual guidelines'}
          </button>
        </div>
      )}
    </section>
  );
}

export default VisualGuidelinesEditor;

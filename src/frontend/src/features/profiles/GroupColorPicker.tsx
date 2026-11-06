import { Check } from 'lucide-react';
import { useI18n } from '../../i18n';
import type { GroupResponse } from '../../shared/api/types';
import { cn, type GroupHue } from '../../shared/ui';

const HUES: GroupHue[] = [
  'slate',
  'blue',
  'teal',
  'green',
  'amber',
  'orange',
  'red',
  'violet',
];

const HUE_CLASSES: Record<GroupHue, string> = {
  slate: 'bg-group-slate',
  blue: 'bg-group-blue',
  teal: 'bg-group-teal',
  green: 'bg-group-green',
  amber: 'bg-group-amber',
  orange: 'bg-group-orange',
  red: 'bg-group-red',
  violet: 'bg-group-violet',
};

export function GroupColorPicker({
  value,
  onChange,
}: {
  value: GroupResponse['color'];
  onChange: (color: GroupResponse['color']) => void;
}) {
  const { t } = useI18n();
  return (
    <div
      role="group"
      aria-label={t('groupColorPalette')}
      data-testid="group-color-picker"
      className="flex flex-wrap items-center gap-xs"
    >
      {HUES.map((hue) => {
        const selected = value === hue;
        return (
          <button
            key={hue}
            type="button"
            aria-label={hue}
            aria-pressed={selected}
            data-testid={`group-color-${hue}`}
            onClick={() => onChange(hue)}
            className={cn(
              'inline-flex h-6 w-6 items-center justify-center rounded-full border-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus',
              HUE_CLASSES[hue],
              selected ? 'border-on-surface' : 'border-outline',
            )}
          >
            {selected && (
              <Check aria-hidden="true" className="h-3 w-3 text-on-accent" />
            )}
          </button>
        );
      })}
    </div>
  );
}

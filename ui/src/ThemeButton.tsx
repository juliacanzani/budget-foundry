import { IconButton } from '@tangible/ui';
import { MoonOutline, SunOutline } from '@tangible/ui/icons/system/index.js';
import type { Mode } from './theme';

const NEXT: Record<Mode, Mode> = { light: 'dark', dark: 'system', system: 'light' };
const NAME: Record<Mode, string> = { light: 'Light', dark: 'Dark', system: 'System' };

export const themeLabel = (mode: Mode, resolved: 'light' | 'dark') =>
  `Theme: ${NAME[mode]}${mode === 'system' ? ` (${resolved})` : ''}. Click to change`;

/**
 * Shows the theme in use and cycles Light → Dark → System. In System the icon is the
 * theme the device resolved to, and the label says so. The tooltip repeats the label,
 * so showTooltip makes it a label tooltip: shown, not read a second time.
 */
export function ThemeButton({ mode, resolved, onChange }: { mode: Mode; resolved: 'light' | 'dark'; onChange: (m: Mode) => void }) {
  return (
    <IconButton
      icon={resolved === 'dark' ? MoonOutline : SunOutline}
      label={themeLabel(mode, resolved)}
      showTooltip
      tooltipSide="bottom"
      variant="ghost"
      size="sm"
      onClick={() => onChange(NEXT[mode])}
    />
  );
}

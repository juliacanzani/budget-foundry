import { IconButton, Tooltip } from '@tangible/ui';
import type { Mode } from './theme';

const NEXT: Record<Mode, Mode> = { light: 'dark', dark: 'system', system: 'light' };
const NAME: Record<Mode, string> = { light: 'Light', dark: 'Dark', system: 'System' };

export const themeLabel = (mode: Mode, resolved: 'light' | 'dark') =>
  `Theme: ${NAME[mode]}${mode === 'system' ? ` (${resolved})` : ''}. Click to change`;

/**
 * Shows the theme in use and cycles Light → Dark → System. In System the icon is the
 * theme the device resolved to, and the label says so. The tooltip hangs off a wrapper,
 * not the button: TUI's Tooltip sets aria-describedby on its trigger, and with the same
 * text as the label that would be read twice. Focus still opens it, by bubbling.
 * Upstream fix accepted (Tooltip type="label", and IconButton showTooltip using it):
 * drop the wrapper for that once it's in a released version.
 */
export function ThemeButton({ mode, resolved, onChange }: { mode: Mode; resolved: 'light' | 'dark'; onChange: (m: Mode) => void }) {
  const label = themeLabel(mode, resolved);
  return (
    <Tooltip>
      <Tooltip.Trigger asChild>
        <span className="theme-button">
          <IconButton
            icon={resolved === 'dark' ? 'system/moon-outline' : 'system/sun-outline'}
            label={label}
            variant="ghost"
            size="sm"
            onClick={() => onChange(NEXT[mode])}
          />
        </span>
      </Tooltip.Trigger>
      <Tooltip.Content side="bottom" className="theme-tooltip">{label}</Tooltip.Content>
    </Tooltip>
  );
}

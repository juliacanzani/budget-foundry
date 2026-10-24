import { useEffect, useState } from 'react';

// Light, dark or the device's, remembered per browser. Shared by the app and the specimen.
export type Mode = 'system' | 'light' | 'dark';
const MODE_KEY = 'budget-foundry:mode';

export const systemTheme = (): 'light' | 'dark' => (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');

function readMode(): Mode {
  try { const m = localStorage.getItem(MODE_KEY); if (m === 'light' || m === 'dark') return m; } catch { /* private mode */ }
  return 'system';
}

/** The chosen mode, or the OS's, resolved to an explicit light or dark (TUI reads data-theme). */
export function useTheme() {
  const mq = window.matchMedia('(prefers-color-scheme: dark)');
  const [system, setSystem] = useState(mq.matches);
  const [mode, setModeState] = useState<Mode>(readMode);
  useEffect(() => {
    const on = (e: MediaQueryListEvent) => setSystem(e.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, [mq]);
  const setMode = (m: Mode) => {
    setModeState(m);
    try { if (m === 'system') localStorage.removeItem(MODE_KEY); else localStorage.setItem(MODE_KEY, m); } catch { /* not saved */ }
  };
  const theme: 'light' | 'dark' = mode === 'system' ? (system ? 'dark' : 'light') : mode;
  useEffect(() => { document.documentElement.style.colorScheme = theme; }, [theme]);
  return { theme, mode, setMode };
}

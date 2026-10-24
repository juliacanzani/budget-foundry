import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import '@tangible/ui/styles';
import './theme.css';
import './app.css';
import { App } from './App';

const queryClient = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } } });

export type Mode = 'system' | 'light' | 'dark';
const MODE_KEY = 'budget-foundry:mode';

function readMode(): Mode {
  try { const m = localStorage.getItem(MODE_KEY); if (m === 'light' || m === 'dark') return m; } catch { /* private mode */ }
  return 'system';
}

/** The chosen mode, or the OS's, resolved to an explicit light or dark (TUI reads data-theme). */
function useTheme() {
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
  const theme = mode === 'system' ? (system ? 'dark' : 'light') : mode;
  return { theme, mode, setMode };
}

function Root() {
  const { theme, mode, setMode } = useTheme();
  useEffect(() => { document.documentElement.style.colorScheme = theme; }, [theme]);
  return (
    <div className="tui-interface tui-font-sans app-root" data-theme={theme}>
      <QueryClientProvider client={queryClient}>
        <App mode={mode} onModeChange={setMode} />
      </QueryClientProvider>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(<StrictMode><Root /></StrictMode>);

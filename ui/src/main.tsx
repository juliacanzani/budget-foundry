import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import '@tangible/ui/styles';
import './app.css';
import { App } from './App';

const queryClient = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } } });

/** Follow the OS, resolved to an explicit light or dark (TUI reads data-theme). */
function useSystemTheme() {
  const mq = window.matchMedia('(prefers-color-scheme: dark)');
  const [dark, setDark] = useState(mq.matches);
  useEffect(() => {
    const on = (e: MediaQueryListEvent) => setDark(e.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, [mq]);
  return dark ? 'dark' : 'light';
}

function Root() {
  const theme = useSystemTheme();
  useEffect(() => { document.documentElement.style.colorScheme = theme; }, [theme]);
  return (
    <div className="tui-interface tui-font-sans app-root" data-theme={theme}>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(<StrictMode><Root /></StrictMode>);

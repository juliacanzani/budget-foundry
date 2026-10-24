import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import '@tangible/ui/styles';
import './theme.css';
import './app.css';
import { App } from './App';
import { useTheme } from './theme';

const queryClient = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } } });

function Root() {
  const { theme, mode, setMode } = useTheme();
  return (
    <div className="tui-interface tui-font-sans app-root" data-theme={theme}>
      <QueryClientProvider client={queryClient}>
        <App mode={mode} resolved={theme} onModeChange={setMode} />
      </QueryClientProvider>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(<StrictMode><Root /></StrictMode>);

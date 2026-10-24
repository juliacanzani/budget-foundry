import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The UI ships inside the Python package; `budget-foundry serve` hosts it.
export default defineConfig({
  plugins: [react()],
  build: { outDir: '../src/budget_foundry/web', emptyOutDir: true },
  server: { proxy: { '/api': 'http://127.0.0.1:8765' } },
});

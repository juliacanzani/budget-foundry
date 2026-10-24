import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

// TUI's icon registry, swapped for an empty one in both builds (see src/icon-registry.ts)
export const iconRegistryAlias = {
  find: /^.*\/icons\/registry\.js$/,
  replacement: fileURLToPath(new URL('src/icon-registry.ts', import.meta.url)),
};

// The UI ships inside the Python package; `budget-foundry serve` hosts it.
export default defineConfig({
  plugins: [react()],
  resolve: { alias: [iconRegistryAlias] },
  build: { outDir: '../src/budget_foundry/web', emptyOutDir: true },
  server: { proxy: { '/api': 'http://127.0.0.1:8765' } },
});

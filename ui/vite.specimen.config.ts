import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

// The specimen ships as one HTML file (exported next to the font), so it builds to a
// single script and stylesheet that budget_foundry/specimen.py inlines with the data.
export default defineConfig({
  plugins: [react()],
  // TUI's full icon registry, swapped for the handful the specimen uses (see src/specimen/icons.ts)
  resolve: { alias: [{ find: /^.*\/icons\/registry\.js$/, replacement: fileURLToPath(new URL('src/specimen/icons.ts', import.meta.url)) }] },
  define: { 'process.env.NODE_ENV': JSON.stringify('production') },
  build: {
    outDir: '../src/budget_foundry/web/specimen',
    emptyOutDir: true,
    lib: { entry: 'src/specimen/main.tsx', formats: ['iife'], name: 'Specimen', fileName: () => 'specimen.js', cssFileName: 'specimen' },
  },
});

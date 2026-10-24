import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { iconRegistryAlias } from './vite.config';

// The specimen ships as one HTML file (exported next to the font), so it builds to a
// single script and stylesheet that budget_foundry/specimen.py inlines with the data.
export default defineConfig({
  plugins: [react()],
  resolve: { alias: [iconRegistryAlias] },
  define: { 'process.env.NODE_ENV': JSON.stringify('production') },
  build: {
    outDir: '../src/budget_foundry/web/specimen',
    emptyOutDir: true,
    lib: { entry: 'src/specimen/main.tsx', formats: ['iife'], name: 'Specimen', fileName: () => 'specimen.js', cssFileName: 'specimen' },
  },
});

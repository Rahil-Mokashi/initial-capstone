/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

// Dev only: the Vite server forwards /api to the local sidecar and adds the
// launch secret, so the browser never needs it. Production is same-origin
// (the sidecar serves the built UI), so no proxy or CORS exists there.
const target = process.env.PPERP_DEV_API ?? 'http://127.0.0.1:8765';
const secret = process.env.PPERP_API_SECRET ?? 'dev-secret';

const version = (JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8')) as { version: string }).version;

export default defineConfig({
  define: { __APP_VERSION__: JSON.stringify(version) },
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    host: '127.0.0.1',
    proxy: { '/api': { target, changeOrigin: false, headers: { 'X-Launch-Secret': secret } } },
  },
  build: { outDir: 'dist', sourcemap: false, target: 'chrome130' },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
});

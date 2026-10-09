// Bundles the Electron main process and the preload scripts. The preload runs in a
// sandbox that cannot require() anything but electron, so it must be one self-contained file.
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { copyFileSync, mkdirSync } from 'node:fs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const common = {
  bundle: true,
  platform: 'node',
  format: 'cjs',
  target: 'node22',
  sourcemap: false,
  external: ['electron'],
  alias: { '@': resolve(root, 'src') },
  logLevel: 'info',
};

await build({
  ...common,
  entryPoints: [resolve(root, 'src/main.ts')],
  outfile: resolve(root, 'dist/main.js'),
});
await build({
  ...common,
  entryPoints: [resolve(root, 'src/preload.ts')],
  outfile: resolve(root, 'dist/preload.js'),
});
await build({
  ...common,
  entryPoints: [resolve(root, 'src/preload-error.ts')],
  outfile: resolve(root, 'dist/preload-error.js'),
});

mkdirSync(resolve(root, 'dist'), { recursive: true });
copyFileSync(resolve(root, 'src/error.html'), resolve(root, 'dist/error.html'));
console.log('desktop build complete');

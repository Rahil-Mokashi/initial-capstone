// Regenerates src/api/schema.d.ts from the FastAPI OpenAPI schema so the
// front end and back end types cannot drift. Run: npm run api:types
import { spawnSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const web = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const root = resolve(web, '..');
const spec = resolve(web, 'src/api/openapi.json');
const types = resolve(web, 'src/api/schema.d.ts');
const python = process.env.PPERP_PYTHON ?? 'python';

function run(cmd, args, cwd) {
  const r = spawnSync(cmd, args, { cwd, stdio: 'inherit', shell: process.platform === 'win32' });
  if (r.status !== 0) process.exit(r.status ?? 1);
}

run(python, ['-m', 'api.export_openapi', spec], root);
run('npx', ['openapi-typescript', spec, '-o', types], web);
console.log('API types regenerated.');

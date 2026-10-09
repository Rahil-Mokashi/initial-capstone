import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, rmSync } from 'node:fs';
import { resolve } from 'node:path';

export const desktopDir = resolve(__dirname, '..');
export const repoRoot = resolve(desktopDir, '..');
export const templateDb = resolve(desktopDir, 'test-results', 'template', 'template.db');

/** Seeds ONE template database; every test then copies it, so tests never share state. */
export default function globalSetup(): void {
  if (!existsSync(resolve(repoRoot, 'web', 'dist', 'index.html'))) {
    throw new Error('web/dist is missing. Run "npm run build" in web/ first.');
  }
  const dir = resolve(desktopDir, 'test-results', 'template');
  rmSync(dir, { recursive: true, force: true });
  mkdirSync(dir, { recursive: true });
  const result = spawnSync(process.env.PPERP_PYTHON ?? 'python', ['desktop/e2e/seed_e2e.py'], {
    cwd: repoRoot,
    env: { ...process.env, PETROL_PUMP_DB_PATH: templateDb, PYTHONUTF8: '1' },
    encoding: 'utf8',
  });
  if (result.status !== 0) throw new Error(`E2E seed failed:\n${result.stdout}\n${result.stderr}`);
}

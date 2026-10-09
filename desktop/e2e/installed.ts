import { chromium, test, type Browser } from '@playwright/test';
import { execSync, spawn, spawnSync, type ChildProcess } from 'node:child_process';
import { copyFileSync, mkdirSync } from 'node:fs';
import { createServer } from 'node:net';
import { join } from 'node:path';
import { templateDb } from './global-setup';

// Helpers for tests of the INSTALLED app. Its Electron fuses switch the Node inspector off, so Playwright's
// Electron mode cannot drive it; these attach over Chromium's own remote-debugging port instead.

export function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const s = createServer();
    s.once('error', reject);
    s.listen(0, '127.0.0.1', () => {
      const port = (s.address() as { port: number }).port;
      s.close(() => resolve(port));
    });
  });
}

export function cleanEnv(extra: Record<string, string>): Record<string, string> {
  const env: Record<string, string> = {};
  for (const [k, v] of Object.entries(process.env)) if (v !== undefined) env[k] = v;
  delete env.ELECTRON_RUN_AS_NODE;
  delete env.PPERP_E2E; // production behaviour: no test hooks
  return Object.assign(env, extra);
}

export async function attach(port: number): Promise<Browser> {
  const deadline = Date.now() + 60_000;
  for (;;) {
    try {
      return await chromium.connectOverCDP(`http://127.0.0.1:${port}`);
    } catch (error) {
      if (Date.now() > deadline) throw error;
      await new Promise((r) => setTimeout(r, 300));
    }
  }
}

export async function firstPage(browser: Browser) {
  const deadline = Date.now() + 60_000;
  for (;;) {
    const page = browser.contexts()[0]?.pages()[0];
    if (page) return page;
    if (Date.now() > deadline) throw new Error('the app opened no window');
    await new Promise((r) => setTimeout(r, 250));
  }
}

export function prepare(dir: string): { env: Record<string, string>; dbPath: string } {
  mkdirSync(dir, { recursive: true });
  const dbPath = join(dir, 'pump.db');
  copyFileSync(templateDb, dbPath); // never the real %LOCALAPPDATA% database
  return { dbPath, env: { PPERP_USER_DATA: join(dir, 'userData'), PETROL_PUMP_DB_PATH: dbPath } };
}

export const sidecarRunning = () =>
  execSync('tasklist /FI "IMAGENAME eq pperp-api.exe" /NH', { encoding: 'utf8' }).includes(
    'pperp-api.exe',
  );

export const spawned: ChildProcess[] = [];
export function track(
  file: string,
  args: string[],
  options: Parameters<typeof spawn>[2],
): ChildProcess {
  const child = spawn(file, args, options);
  spawned.push(child);
  return child;
}
/** Used in finally blocks so a failed test never leaves an app (and its service) running. */
export function forceStop(child: ChildProcess): void {
  spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true });
}

export function closeGracefully(child: ChildProcess): void {
  // Without /F this is a normal close request, like clicking the window's X.
  spawnSync('taskkill', ['/pid', String(child.pid)], { windowsHide: true });
}

test.afterEach(() => {
  for (const child of spawned.splice(0)) forceStop(child);
});

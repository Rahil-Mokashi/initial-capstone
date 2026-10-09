import {
  test as base,
  _electron as electron,
  expect,
  type ElectronApplication,
  type Page,
} from '@playwright/test';
import { copyFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { desktopDir, repoRoot, templateDb } from './global-setup';

export { expect };
export const PASSWORD = 'Passw0rd!x';

export interface Launched {
  app: ElectronApplication;
  page: Page;
  dbPath: string;
  userData: string;
  /** Every URL any page requested (even ones the blocker later cancelled). */
  requested: string[];
}

export async function launchApp(
  dir: string,
  opts: { userData?: string; dbPath?: string } = {},
): Promise<Launched> {
  mkdirSync(dir, { recursive: true });
  const dbPath = opts.dbPath ?? join(dir, 'pump.db');
  if (!opts.dbPath) copyFileSync(templateDb, dbPath);
  const userData = opts.userData ?? join(dir, 'userData');

  const env: Record<string, string> = {};
  for (const [k, v] of Object.entries(process.env)) if (v !== undefined) env[k] = v;
  // This variable (set by some IDE terminals) makes Electron behave as plain Node.
  delete env.ELECTRON_RUN_AS_NODE;
  Object.assign(env, {
    PPERP_E2E: '1',
    PPERP_USER_DATA: userData,
    PETROL_PUMP_DB_PATH: dbPath,
    PPERP_WEB_DIR: join(repoRoot, 'web', 'dist'),
    PYTHONUTF8: '1',
    // What the file dialog returns in tests (a native dialog cannot be clicked in an automated run).
    PPERP_E2E_PICK_PATH: 'C:\\docs\\id-proof.pdf',
  });

  const app = await electron.launch({ args: [desktopDir], cwd: desktopDir, env });
  const requested: string[] = [];
  app.context().on('request', (request) => requested.push(request.url()));
  const page = await app.firstWindow();
  return { app, page, dbPath, userData, requested };
}

export async function signIn(page: Page, username: string, password = PASSWORD): Promise<void> {
  await page.getByLabel('Username').fill(username);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
}

export const test = base.extend<{ launched: Launched }>({
  // eslint-disable-next-line no-empty-pattern -- Playwright requires a destructuring pattern here
  launched: async ({}, use, testInfo) => {
    const launched = await launchApp(testInfo.outputPath('run'));
    await expect(launched.page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
    await use(launched);
    await launched.app.close().catch(() => undefined);
  },
});

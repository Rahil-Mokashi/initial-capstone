import { _electron as electron, expect, test } from '@playwright/test';
import { execSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

// The installed app, placed in a DELIBERATELY deep folder, must explain the problem instead of crashing.
// Opt-in: PPERP_DEEP_EXE=<path to the Petrol Pump ERP.exe installed in a path longer than ~130 characters>
const exe = process.env.PPERP_DEEP_EXE;
test.skip(!exe, 'set PPERP_DEEP_EXE to an installation in a very deep folder');

// eslint-disable-next-line no-empty-pattern -- Playwright requires a destructuring pattern
test('a too-long install path shows a clear message and does not start the service', async ({}, testInfo) => {
  const dir = testInfo.outputPath('deep');
  mkdirSync(dir, { recursive: true });
  const env: Record<string, string> = {};
  for (const [k, v] of Object.entries(process.env)) if (v !== undefined) env[k] = v;
  delete env.ELECTRON_RUN_AS_NODE;
  Object.assign(env, {
    PPERP_USER_DATA: join(dir, 'ud'),
    PETROL_PUMP_DB_PATH: join(dir, 'pump.db'),
  });

  const app = await electron.launch({ executablePath: exe!, args: [], env });
  const page = await app.firstWindow();
  await expect(
    page.getByRole('heading', { name: 'The application could not start' }),
  ).toBeVisible();
  const text = await page.locator('#details').innerText();
  expect(text).toContain('installed in a folder whose path is too long');
  expect(text).toContain('C:\\PPERP');
  expect(text).toMatch(/at most \d+ characters/);
  const running = execSync('tasklist /FI "IMAGENAME eq pperp-api.exe" /NH', { encoding: 'utf8' });
  expect(running).not.toContain('pperp-api.exe');
  await app.close();
});

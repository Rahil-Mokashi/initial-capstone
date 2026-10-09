import { _electron as electron, expect, test } from '@playwright/test';
import { execSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { templateDb } from './global-setup';

// Smoke test of the INSTALLED application (NSIS build): starts, shows login, Tanks works.
// Runs only when PPERP_PACKAGED_EXE points at the installed "Petrol Pump ERP.exe".
const exe = process.env.PPERP_PACKAGED_EXE;
test.skip(!exe, 'set PPERP_PACKAGED_EXE to the installed app to run the packaged smoke test');

// eslint-disable-next-line no-empty-pattern -- Playwright requires a destructuring pattern
test('the installed app starts, shows login, and the Tanks screen works end to end', async ({}, testInfo) => {
  const dir = testInfo.outputPath('packaged');
  mkdirSync(dir, { recursive: true });
  const dbPath = join(dir, 'pump.db');
  copyFileSync(templateDb, dbPath); // never the real %LOCALAPPDATA% database

  const env: Record<string, string> = {};
  for (const [k, v] of Object.entries(process.env)) if (v !== undefined) env[k] = v;
  delete env.ELECTRON_RUN_AS_NODE;
  Object.assign(env, { PPERP_USER_DATA: join(dir, 'userData'), PETROL_PUMP_DB_PATH: dbPath });
  delete env.PPERP_E2E; // production behaviour: no test hooks

  const started = Date.now();
  const app = await electron.launch({ executablePath: exe!, args: [], env });
  const page = await app.firstWindow();
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible({ timeout: 60_000 });
  const toLogin = Date.now() - started;
  console.log(`PACKAGED start -> login visible: ${toLogin} ms`);

  // The Python service really is the frozen executable inside the installation.
  const procs = execSync('powershell -NoProfile -Command "(Get-Process pperp-api).Path"', {
    encoding: 'utf8',
  });
  expect(procs.toLowerCase()).toContain('resources\\sidecar\\pperp-api\\pperp-api.exe');

  await page.getByLabel('Username').fill('manager1');
  await page.getByLabel('Password').fill('Passw0rd!x');
  await page.getByRole('button', { name: 'Sign in' }).click();
  const t1 = page.getByRole('listitem').filter({ has: page.getByRole('heading', { name: 'T1' }) });
  await expect(t1.getByText('2,500.500')).toBeVisible();
  await t1.getByRole('button', { name: 'Receipt' }).click();
  await page.getByLabel('Quantity (L)').fill('100');
  await page.getByRole('button', { name: 'Record receipt' }).click();
  await expect(t1.getByText('2,600.500')).toBeVisible();

  await app.close();
  await expect
    .poll(() => (existsSync(`${dbPath}-wal`) ? statSync(`${dbPath}-wal`).size : 0), {
      timeout: 20_000,
    })
    .toBe(0);
  expect(
    execSync('tasklist /FI "IMAGENAME eq pperp-api.exe" /NH', { encoding: 'utf8' }),
  ).not.toContain('pperp-api.exe');
});

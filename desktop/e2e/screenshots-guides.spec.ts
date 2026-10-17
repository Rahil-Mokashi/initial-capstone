import { spawnSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import type { Page } from '@playwright/test';
import { launchApp, signIn, test, expect, apiAs } from './fixtures';
import { MainPcFixture } from './lanFixture';
import { repoRoot } from './global-setup';

// Only when asked: SCREENSHOTS=1 npx playwright test e2e/screenshots-guides.spec.ts
// The pictures in docs/guides/img/, taken from the real screens on SYNTHETIC data (e2e/seed_demo_day.py): no real names or figures.
test.skip(process.env.SCREENSHOTS !== '1', 'screenshots are generated on demand');
test.setTimeout(600_000);

const out = resolve(repoRoot, 'docs', 'guides', 'img');
const missed: string[] = [];

async function shot(page: Page, name: string) {
  await page.waitForTimeout(700);
  await page.screenshot({ path: join(out, `${name}.png`) });
}

/** Opens a screen by its route and takes the picture. A screen that does not open is listed, not fatal. */
async function snap(page: Page, name: string, hash: string) {
  try {
    await page.evaluate((h) => (location.hash = h), hash);
    await page.locator('main h1').first().waitFor({ timeout: 8000 });
    await shot(page, name);
  } catch {
    missed.push(`${name} (${hash})`);
  }
}

// eslint-disable-next-line no-empty-pattern -- Playwright requires a destructuring pattern here
test('the screens of the user guide', async ({}, testInfo) => {
  mkdirSync(out, { recursive: true });
  const dir = testInfo.outputPath('demo');
  mkdirSync(dir, { recursive: true });
  const dbPath = join(dir, 'demo.db');
  const seeded = spawnSync(process.env.PPERP_PYTHON ?? 'python', ['desktop/e2e/seed_demo_day.py'], {
    cwd: repoRoot,
    env: { ...process.env, PETROL_PUMP_DB_PATH: dbPath, PYTHONUTF8: '1' },
    encoding: 'utf8',
  });
  if (seeded.status !== 0) throw new Error(`demo seed failed:\n${seeded.stdout}\n${seeded.stderr}`);

  // --- sign-in, then the owner's screens
  let run = await launchApp(join(dir, 'owner'), { dbPath });
  await run.page.setViewportSize({ width: 1360, height: 860 });
  await expect(run.page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  await shot(run.page, 'sign-in');
  await signIn(run.page, 'owner1', undefined, { home: true });
  await run.page.locator('main h1').first().waitFor();
  await shot(run.page, 'today');
  for (const [name, hash] of [
    ['more', '#/more'], ['alerts', '#/alerts'], ['tanks', '#/tanks'], ['employees', '#/employees'], ['users', '#/users'],
    ['fuel-prices', '#/fuel-prices'], ['nozzles', '#/nozzles'], ['suppliers', '#/procurement?tab=suppliers'],
    ['purchase-orders', '#/procurement?tab=orders'], ['shifts', '#/shifts'], ['attendance', '#/attendance'], ['leave', '#/leave'],
    ['sales', '#/sales'], ['checks', '#/checks'], ['review', '#/review'], ['daily-report', '#/daily-report'], ['digest', '#/digest'],
    ['credit', '#/credit'], ['credit-ageing', '#/credit/ageing'], ['bank', '#/bank'], ['payroll', '#/payroll'],
    ['lubricants', '#/lubricants'], ['bowser', '#/bowser'], ['expenses', '#/expenses'], ['reconciliation', '#/reconciliation'],
    ['reports', '#/reports'], ['analytics', '#/analytics'], ['company-profile', '#/settings'], ['owner-choices', '#/owner-choices'],
    ['backups', '#/backups'], ['devices', '#/devices'], ['system-health', '#/system-health'], ['email-summary', '#/mail'],
    ['audit-log', '#/audit'], ['support', '#/support'], ['close-shift-owner', '#/close-shift'], ['shift-totals', '#/shift-totals'],
  ] as const) {
    await snap(run.page, name, hash);
  }

  // the tanks: numbers on, one tank opened, its dip chart
  try {
    await run.page.evaluate(() => (location.hash = '#/tanks'));
    await run.page.getByRole('checkbox', { name: 'Show numbers' }).check();
    await shot(run.page, 'tanks-with-numbers');
    await run.page.getByRole('checkbox', { name: 'Show numbers' }).uncheck();
    await run.page.getByRole('link', { name: 'MS-22' }).first().click();
    await run.page.locator('main h1').first().waitFor();
    await shot(run.page, 'tank-detail');
    await run.page.getByRole('button', { name: 'Dip chart' }).click();
    await run.page.getByLabel('Row 1 dip in cm').fill('0');
    await run.page.getByLabel('Row 1 litres').fill('0');
    await run.page.getByRole('button', { name: /Add a row/ }).click();
    await run.page.getByLabel('Row 2 dip in cm').fill('120');
    await run.page.getByLabel('Row 2 litres').fill('35485');
    await shot(run.page, 'dip-chart');
    await run.page.getByRole('button', { name: 'Close', exact: true }).first().click();
  } catch {
    missed.push('tanks detail / dip chart');
  }
  // the search box
  try {
    await run.page.evaluate(() => (location.hash = '#/'));
    await run.page.keyboard.press('Control+k');
    await run.page.keyboard.type('nozel');
    await shot(run.page, 'search');
  } catch {
    missed.push('search');
  }
  // the account menu
  try {
    await run.page.keyboard.press('Escape');
    await run.page.getByRole('button', { name: /Account menu/ }).click();
    await shot(run.page, 'account-menu');
  } catch {
    missed.push('account menu');
  }
  await run.app.close().catch(() => undefined);

  // --- the data-entry person: the Terminal and the Close Shift desk
  run = await launchApp(join(dir, 'entry'), { dbPath });
  await run.page.setViewportSize({ width: 1360, height: 860 });
  await signIn(run.page, 'dataentry1', undefined, { home: true });
  await run.page.locator('main h1').first().waitFor();
  await shot(run.page, 'today-data-entry');
  try {
    await run.page.evaluate(() => (location.hash = '#/terminal'));
    await run.page.getByRole('heading', { level: 1, name: 'Terminal' }).waitFor();
    await run.page.getByLabel(/^Customer/).selectOption({ label: '+ New customer' });
    await run.page.getByLabel('New customer name').fill('Sample Roadways');
    await run.page.getByLabel('Vehicle number').fill('MH 12 AB 1234');
    await shot(run.page, 'terminal-credit-new-customer');
    await run.page.getByRole('button', { name: 'DTP Card' }).click();
    await shot(run.page, 'terminal-dtp');
  } catch {
    missed.push('terminal');
  }
  await snap(run.page, 'close-shift', '#/close-shift');
  await run.app.close().catch(() => undefined);

  writeFileSync(join(out, '_missed.txt'), missed.join('\n') || 'nothing missed');
  expect(missed, 'screens that did not open').toEqual([]);
});

// eslint-disable-next-line no-empty-pattern -- Playwright requires a destructuring pattern here
test('the network setup pictures', async ({}, testInfo) => {
  mkdirSync(out, { recursive: true });
  const pc = await MainPcFixture.start(testInfo.outputPath('main-pc'), { webDir: join(repoRoot, 'web', 'dist') });
  const a = await launchApp(testInfo.outputPath('client'));
  try {
    const opened = a.app.waitForEvent('window');
    await a.page.getByRole('button', { name: 'Network setup' }).click();
    const setup = await opened;
    await setup.setViewportSize({ width: 820, height: 900 });
    await shot(setup, 'network-setup');
    await setup.getByLabel('Main PC address').fill(pc.ready.host);
    await setup.getByLabel('Port', { exact: true }).fill(String(pc.ready.port));
    await setup.getByLabel('Pairing port').fill(String(pc.ready.pairing_port));
    await setup.getByLabel('Name for this PC').fill('Counter PC');
    const { code } = await pc.pair();
    await setup.getByLabel('Pairing code').fill(code);
    await shot(setup, 'network-setup-filled');
    await setup.getByRole('button', { name: 'Check the Main PC' }).click();
    await expect(setup.locator('#fingerprint')).not.toBeEmpty();
    await shot(setup, 'network-setup-fingerprint');
    await setup.getByRole('button', { name: /They match/ }).click();
    await setup.waitForEvent('close');
    let page: Page | undefined;
    for (let i = 0; i < 40 && !page; i++) {
      page = a.app.windows().find((x) => x.url().startsWith('http://127.0.0.1'));
      if (!page) await new Promise((r) => setTimeout(r, 500));
    }
    await expect(page!.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
    await signIn(page!, 'owner1');
    await page!.setViewportSize({ width: 1360, height: 860 });
    await page!.evaluate(() => (location.hash = '#/devices'));
    await expect(page!.getByRole('heading', { name: 'Devices' })).toBeVisible();
    await shot(page!, 'devices');
    await page!.getByRole('button', { name: 'Add a device' }).click();
    await expect(page!.getByLabel('Pairing code')).toBeVisible();
    await shot(page!, 'devices-add');
    await page!.getByRole('button', { name: 'Done' }).click();
    void apiAs;
  } finally {
    await a.app.close().catch(() => undefined);
    await pc.stop();
  }
});

import { spawnSync } from 'node:child_process';
import { mkdirSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { expect, launchApp, signIn, test } from './fixtures';
import { repoRoot } from './global-setup';

// Only when asked: SCREENSHOTS=1 npx playwright test e2e/screenshots-12h.spec.ts
// Screenshots of the site-visit screens on SYNTHETIC data (e2e/seed_demo_day.py), written to docs/screenshots/12h/.
test.skip(process.env.SCREENSHOTS !== '1', 'screenshots are generated on demand');
test.setTimeout(240_000);

const out = resolve(repoRoot, 'docs', 'screenshots', '12h');

// eslint-disable-next-line no-empty-pattern -- Playwright requires a destructuring pattern here
test('screens of the site-visit build on synthetic data', async ({}, testInfo) => {
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

  const shot = async (page: import('@playwright/test').Page, name: string) => {
    await page.waitForTimeout(700);
    await page.screenshot({ path: join(out, `${name}.png`) });
  };
  const go = async (
    page: import('@playwright/test').Page,
    hash: string,
    heading: RegExp | string,
  ) => {
    await page.evaluate((h) => (location.hash = h), hash);
    await expect(page.getByRole('heading', { level: 1, name: heading }).first()).toBeVisible();
  };

  // --- owner
  let run = await launchApp(join(dir, 'owner'), { dbPath });
  await run.page.setViewportSize({ width: 1360, height: 900 });
  await signIn(run.page, 'owner1', undefined, { home: true });
  await expect(run.page.getByText(/checks passed|No checks/).first()).toBeVisible();
  await shot(run.page, 'today-owner');
  await go(run.page, '#/checks', 'Checks');
  await shot(run.page, 'checks');
  await go(run.page, '#/daily-report', 'Daily Report');
  await run.page.getByLabel('Style').selectOption('classic');
  await expect(run.page.getByRole('table').first()).toBeVisible();
  await shot(run.page, 'daily-report-screen');
  await go(run.page, '#/credit/ageing', 'Credit Ageing');
  await shot(run.page, 'credit-ageing');
  await go(run.page, '#/credit', 'Credit Management');
  await run.page.getByRole('link', { name: 'Old Debtor Traders' }).click();
  await expect(run.page.getByRole('heading', { name: 'Old Debtor Traders' })).toBeVisible();
  await shot(run.page, 'credit-customer');

  // the Classic and Plus printouts, rendered by the app's own browser from the real API output
  for (const style of ['classic', 'plus']) {
    const html = (await run.page.evaluate(async (s) => {
      const b = window.pperp!;
      const login = await fetch(`${b.apiBase}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Launch-Secret': b.launchSecret },
        body: JSON.stringify({ username: 'owner1', password: 'Passw0rd!x' }),
      });
      const { token } = (await login.json()) as { token: string };
      const day = new Date().toLocaleDateString('sv');
      const r = await fetch(`${b.apiBase}/api/daily-report?day=${day}&style=${s}`, {
        headers: { 'X-Launch-Secret': b.launchSecret, Authorization: `Bearer ${token}` },
      });
      return ((await r.json()) as { html: string }).html;
    }, style)) as string;
    // the app's own print preview window shows the printout exactly as it prints
    const opened = run.app.waitForEvent('window');
    await run.page.evaluate((h) => window.pperp!.print.preview(h), html);
    const preview = await opened;
    await preview.waitForLoadState('load');
    await preview.waitForTimeout(1200);
    await preview.screenshot({ path: join(out, `daily-report-${style}.png`), fullPage: true });
    await preview.close();
  }
  await run.app.close().catch(() => undefined);

  // --- accountant
  run = await launchApp(join(dir, 'acc'), { dbPath });
  await run.page.setViewportSize({ width: 1360, height: 900 });
  await signIn(run.page, 'accountant1', undefined, { home: true });
  await go(run.page, '#/bank', 'Bank Matching');
  await expect(
    run.page.getByRole('table', { name: 'Expected against received, by day' }),
  ).toBeVisible();
  await shot(run.page, 'bank-matching');
  await go(run.page, '#/payroll', 'Payroll');
  await run.page
    .getByLabel('Month')
    .fill(
      new Date(new Date().getFullYear(), new Date().getMonth() - 1, 1)
        .toLocaleDateString('sv')
        .slice(0, 7),
    );
  await expect(run.page.getByRole('table', { name: /Salary register/ })).toBeVisible();
  await shot(run.page, 'payroll-register');
  await run.app.close().catch(() => undefined);

  // --- data entry
  run = await launchApp(join(dir, 'de'), { dbPath });
  await run.page.setViewportSize({ width: 1360, height: 900 });
  await signIn(run.page, 'dataentry1', undefined, { home: true });
  await expect(run.page.getByRole('region', { name: /Shift entry/ })).toBeVisible();
  await shot(run.page, 'today-data-entry');
  await run.app.close().catch(() => undefined);
  expect(readFileSync(join(out, 'today-owner.png')).length).toBeGreaterThan(1000);
});

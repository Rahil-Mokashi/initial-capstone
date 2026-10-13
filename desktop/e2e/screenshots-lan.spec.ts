import { mkdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { expect, launchApp, signIn, test } from './fixtures';
import { MainPcFixture } from './lanFixture';
import { repoRoot } from './global-setup';

// Only when asked: SCREENSHOTS=1 npx playwright test e2e/screenshots-lan.spec.ts   (synthetic data only)
test.skip(process.env.SCREENSHOTS !== '1', 'screenshots are generated on demand');
test.setTimeout(240_000);
const out = resolve(repoRoot, 'docs', 'screenshots', 'lan');

// eslint-disable-next-line no-empty-pattern -- Playwright requires a destructuring pattern here
test('network setup, devices and the unreachable screen', async ({}, testInfo) => {
  mkdirSync(out, { recursive: true });
  const pc = await MainPcFixture.start(testInfo.outputPath('main-pc'), { webDir: join(repoRoot, 'web', 'dist') });
  const a = await launchApp(testInfo.outputPath('client'));
  const shot = async (page: import('@playwright/test').Page, name: string) => {
    await page.waitForTimeout(600);
    await page.screenshot({ path: join(out, `${name}.png`) });
  };
  try {
    const opened = a.app.waitForEvent('window');
    await a.page.getByRole('button', { name: 'Network setup' }).click();
    const setup = await opened;
    await setup.setViewportSize({ width: 820, height: 800 });
    await shot(setup, 'network-setup');
    await setup.getByLabel('Main PC address').fill(pc.ready.host);
    await setup.getByLabel('Port', { exact: true }).fill(String(pc.ready.port));
    await setup.getByLabel('Pairing port').fill(String(pc.ready.pairing_port));
    await setup.getByLabel('Name for this PC').fill('Counter PC');
    const { code } = await pc.pair();
    await setup.getByLabel('Pairing code').fill(code);
    await setup.getByRole('button', { name: 'Check the Main PC' }).click();
    await expect(setup.locator('#fingerprint')).not.toBeEmpty();
    await shot(setup, 'network-setup-fingerprint');
    await setup.getByRole('button', { name: /They match/ }).click();
    await setup.waitForEvent('close');
    const find = async () => {
      for (let i = 0; i < 40; i++) {
        const w = a.app.windows().find((x) => x.url().startsWith('http://127.0.0.1'));
        if (w) return w;
        await new Promise((r) => setTimeout(r, 500));
      }
      throw new Error('no client window');
    };
    let page = await find();
    await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
    await shot(page, 'client-sign-in');
    await signIn(page, 'owner1');
    await page.evaluate(() => (location.hash = '#/devices'));
    await expect(page.getByRole('heading', { name: 'Devices' })).toBeVisible();
    await shot(page, 'devices');
    await page.getByRole('button', { name: 'Add a device' }).click();
    await expect(page.getByLabel('Pairing code')).toBeVisible();
    await shot(page, 'devices-add');
    await pc.stop();
    await page.reload();
    page = await find();
    await expect(page.getByText('Cannot reach the Main PC')).toBeVisible();
    await shot(page, 'main-pc-unreachable');
  } finally {
    await a.app.close().catch(() => undefined);
    await pc.stop().catch(() => undefined);
  }
});

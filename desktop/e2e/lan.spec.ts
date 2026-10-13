/* eslint-disable no-empty-pattern -- Playwright requires a destructuring pattern as the first argument */
// Two Client PCs and a Main PC (real mutual TLS on loopback): pairing through the setup window, a device file,
// shared live data, removing a device, and the Main PC going away.
import { join } from 'node:path';
import { type Launched, apiAs, expect, launchApp, setupPump, signIn, test } from './fixtures';
import { MainPcFixture } from './lanFixture';
import { repoRoot } from './global-setup';

let pc: MainPcFixture;
const apps: Launched[] = [];

test.beforeEach(async ({}, testInfo) => {
  pc = await MainPcFixture.start(testInfo.outputPath('main-pc'), { webDir: join(repoRoot, 'web', 'dist') });
});
test.afterEach(async () => {
  for (const a of apps.splice(0)) await a.app.close().catch(() => undefined);
  await pc.stop();
});

async function pairThroughSetup(l: Launched, name: string) {
  const setupOpened = l.app.waitForEvent('window');
  await l.page.getByRole('button', { name: 'Network setup' }).click();
  const setup = await setupOpened;
  await setup.getByLabel('Main PC address').fill(pc.ready.host);
  await setup.getByLabel('Port', { exact: true }).fill(String(pc.ready.port));
  await setup.getByLabel('Pairing port').fill(String(pc.ready.pairing_port));
  await setup.getByLabel('Name for this PC').fill(name);
  const { code, fingerprint } = await pc.pair();
  await setup.getByLabel('Pairing code').fill(code);
  await setup.getByRole('button', { name: 'Check the Main PC' }).click();
  await expect(setup.locator('#fingerprint')).toHaveText(fingerprint.match(/.{1,4}/g)!.join(' ').toUpperCase());
  await setup.getByRole('button', { name: /They match/ }).click();
  await setup.waitForEvent('close');
}

async function clientWindow(l: Launched) {
  // After pairing the shell restarts in Client mode: the first window is the new main window.
  for (let i = 0; i < 40; i++) {
    for (const w of l.app.windows()) if (w.url().startsWith('http://127.0.0.1')) return w;
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error('no client window');
}

test('a PC is paired through Network setup and then works on the Main PC\'s data', async ({}, testInfo) => {
  const a = await launchApp(testInfo.outputPath('client-a'));
  apps.push(a);
  await expect(a.page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  await pairThroughSetup(a, 'Counter PC');
  const page = await clientWindow(a);
  await expect(page.getByText("Your data stays on the pump's Main PC.")).toBeVisible();
  await signIn(page, 'manager1');
  await expect(page.getByRole('heading', { level: 1, name: /Tanks & Inventory/ })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'T1' })).toBeVisible(); // seeded on the Main PC, not on this PC
  // the audit log on the Main PC names this device and its address
  const api = await apiAs(page, 'owner1');
  const audit = (await api('GET', '/audit?event_type=login_success')) as unknown as Array<{ device: string | null }>;
  expect(audit.map((e) => e.device)).toContain('Counter PC (127.0.0.1)');
});

test('two PCs share live data, and a removed PC is locked out', async ({}, testInfo) => {
  const a = await launchApp(testInfo.outputPath('client-a'));
  apps.push(a);
  await pairThroughSetup(a, 'Counter PC');
  const pageA = await clientWindow(a);

  const file = testInfo.outputPath('office.json');
  const { device_id } = await pc.local('Office PC', file);
  const b = await launchApp(testInfo.outputPath('client-b'), { env: { PPERP_E2E_DEVICE_FILE: file } });
  apps.push(b);
  const setupOpened = b.app.waitForEvent('window');
  await b.page.getByRole('button', { name: 'Network setup' }).click();
  const setup = await setupOpened;
  await setup.getByRole('button', { name: 'Import a device file...' }).click();
  await setup.waitForEvent('close');
  const pageB = await clientWindow(b);

  await signIn(pageA, 'manager1');
  await signIn(pageB, 'manager1');
  const apiA = await apiAs(pageA, 'manager1');
  const fuels = (await apiA('GET', '/fuel-prices')) as unknown as Array<{ id: string; fuel_type: string }>;
  await apiA('POST', '/tanks', { code: 'LIVE-1', fuel_id: fuels[0]!.id, capacity: '5000', opening_stock: '100' });
  await pageB.reload(); // a reload ends the session (it lives in memory only): sign in again
  await signIn(pageB, 'manager1');
  await expect(pageB.getByRole('heading', { name: 'LIVE-1' })).toBeVisible(); // written on A, read on B

  // the owner removes Office PC from the Devices screen on A
  await pageA.getByRole('button', { name: /Account menu/ }).click();
  await pageA.getByRole('button', { name: 'Log out' }).click();
  await signIn(pageA, 'owner1');
  await pageA.evaluate(() => (location.hash = '#/devices'));
  await expect(pageA.getByRole('table', { name: 'Devices' })).toContainText('Office PC');
  await pageA.getByRole('button', { name: 'Remove Office PC' }).click();
  await pageA.getByLabel(/Reason for removing/).fill('Replaced');
  await pageA.getByRole('button', { name: 'Remove', exact: true }).click();
  await expect(pageA.getByRole('table', { name: 'Devices' })).toContainText('Removed');
  await pc.revoke(device_id).catch(() => undefined); // already removed: harmless
  await pageB.reload();
  await expect(pageB.getByText('This PC is not allowed on the Main PC')).toBeVisible();
});

test('the window says plainly when the Main PC cannot be reached, and recovers', async ({}, testInfo) => {
  const a = await launchApp(testInfo.outputPath('client-a'));
  apps.push(a);
  await pairThroughSetup(a, 'Counter PC');
  const page = await clientWindow(a);
  await signIn(page, 'manager1');
  await expect(page.getByRole('heading', { level: 1, name: /Tanks & Inventory/ })).toBeVisible();
  await pc.stop();
  await page.reload();
  await expect(page.getByText('Cannot reach the Main PC')).toBeVisible();
});

test('a shift is entered on one PC, verified on a second, approved and locked by an owner, and the second PC sees it live', async ({}, testInfo) => {
  const a = await launchApp(testInfo.outputPath('client-a'));
  apps.push(a);
  await pairThroughSetup(a, 'Counter PC');
  const pageA = await clientWindow(a);
  await setupPump(pageA); // Petrol at 100.00, nozzle N1 (opening 0), an open shift - on the Main PC's database

  const file = testInfo.outputPath('office.json');
  await pc.local('Office PC', file);
  const b = await launchApp(testInfo.outputPath('client-b'), { env: { PPERP_E2E_DEVICE_FILE: file } });
  apps.push(b);
  const setupOpened = b.app.waitForEvent('window');
  await b.page.getByRole('button', { name: 'Network setup' }).click();
  const setup = await setupOpened;
  await setup.getByRole('button', { name: 'Import a device file...' }).click();
  await setup.waitForEvent('close');
  const pageB = await clientWindow(b);

  // 1. the cashier closes the shift on the counter PC
  await pageA.evaluate(() => (location.hash = '#/close-shift'));
  await signIn(pageA, 'dataentry1', undefined, { home: true });
  await pageA.getByLabel('Closing for N1').fill('505');
  await pageA.getByLabel('CARD', { exact: true }).fill('11000');
  await pageA.getByLabel('Advance', { exact: true }).fill('20000');
  await pageA.getByLabel('Final', { exact: true }).fill('14000');
  await expect(pageA.getByText('Balanced')).toBeVisible();
  await pageA.getByRole('button', { name: /Close shift/ }).click();
  await expect(pageA.getByText('Shift closed and saved.')).toBeVisible();

  // 2. the accountant, on the office PC, sees it Entered and verifies it
  await pageB.evaluate(() => (location.hash = '#/review'));
  await signIn(pageB, 'accountant1', undefined, { home: true });
  const row = pageB.getByRole('listitem').filter({ hasText: 'Morning' });
  await expect(row.getByText('Entered', { exact: true }).first()).toBeVisible();
  await row.getByRole('button', { name: /^Verify/ }).click();
  await expect(row.getByText('Verified', { exact: true }).first()).toBeVisible();

  // 3. an owner on the counter PC approves and locks
  await pageA.getByRole('button', { name: /Account menu/ }).click();
  await pageA.getByRole('button', { name: 'Log out' }).click();
  await pageA.evaluate(() => (location.hash = '#/review'));
  await signIn(pageA, 'owner1', undefined, { home: true });
  const ownerRow = pageA.getByRole('listitem').filter({ hasText: 'Morning' });
  await ownerRow.getByRole('button', { name: /^Approve/ }).click();
  await ownerRow.getByRole('button', { name: /^Lock/ }).click();
  await expect(ownerRow.getByText('Locked', { exact: true }).first()).toBeVisible();

  // 4. the accountant's screen changed on its own, with no reload
  await expect(row.getByText('Locked', { exact: true }).first()).toBeVisible({ timeout: 25_000 });
  await expect(row.getByRole('button', { name: /^Verify|^Approve|^Lock/ })).toHaveCount(0);
});

import { expect, test } from '@playwright/test';
import { execSync, spawn, spawnSync } from 'node:child_process';
import { existsSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { desktopDir } from './global-setup';
import {
  attach,
  cleanEnv,
  closeGracefully,
  firstPage,
  freePort,
  prepare,
  sidecarRunning,
  track,
} from './installed';

// Tests of the INSTALLED application (NSIS build). Opt-in: set PPERP_PACKAGED_EXE to the installed
// "Petrol Pump ERP.exe". The build has Electron fuses that disable the Node inspector, so Playwright's
// Electron mode cannot drive it; these tests attach over Chromium's own debugging port instead.
const exe = process.env.PPERP_PACKAGED_EXE;
test.skip(!exe, 'set PPERP_PACKAGED_EXE to the installed app to run the packaged tests');

// eslint-disable-next-line no-empty-pattern -- Playwright requires a destructuring pattern
test('the installed app starts, shows login, and the Tanks screen works end to end', async ({}, testInfo) => {
  const { env, dbPath } = prepare(testInfo.outputPath('packaged'));
  const port = await freePort();
  const started = Date.now();
  const child = track(exe!, [`--remote-debugging-port=${port}`], {
    env: cleanEnv(env),
    windowsHide: false,
  });
  const browser = await attach(port);
  try {
    const page = await firstPage(browser);
    await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible({ timeout: 60_000 });
    console.log(`PACKAGED start -> login visible: ${Date.now() - started} ms`);

    // The Python service really is the frozen executable inside the installation.
    const procs = execSync('powershell -NoProfile -Command "(Get-Process pperp-api).Path"', {
      encoding: 'utf8',
    });
    expect(procs.toLowerCase()).toContain('resources\\api\\pperp-api.exe');

    await page.evaluate(() => (location.hash = '#/tanks')); // the home screen is Today; go to Tanks after sign-in
    await page.getByLabel('Username').fill('manager1');
    await page.getByLabel('Password').fill('Passw0rd!x');
    await page.getByRole('button', { name: 'Sign in' }).click();
    const t1 = page
      .getByRole('listitem')
      .filter({ has: page.getByRole('heading', { name: 'T1' }) });
    await expect(t1.getByText('2,500.500')).toBeVisible();
    await t1.getByRole('button', { name: 'Receipt' }).click();
    await page.getByLabel('Quantity (L)').fill('100');
    await page.getByRole('button', { name: 'Record receipt' }).click();
    await expect(t1.getByText('2,600.500')).toBeVisible();
  } finally {
    await browser.close().catch(() => undefined); // disconnects only
  }

  closeGracefully(child);
  await expect
    .poll(() => (existsSync(`${dbPath}-wal`) ? statSync(`${dbPath}-wal`).size : 0), {
      timeout: 30_000,
    })
    .toBe(0);
  await expect.poll(sidecarRunning, { timeout: 15_000 }).toBe(false);
});

// eslint-disable-next-line no-empty-pattern -- Playwright requires a destructuring pattern
test('ELECTRON_RUN_AS_NODE=1 does NOT turn the installed app into plain Node (fuse), unlike an unfused Electron', async ({}, testInfo) => {
  // Control: the development Electron has no such fuse, so the variable really does switch it to Node mode.
  const devElectron = join(desktopDir, 'node_modules', 'electron', 'dist', 'electron.exe');
  const control = spawnSync(devElectron, ['-e', 'console.log("NODE-MODE-ACTIVE")'], {
    env: { ...cleanEnv({}), ELECTRON_RUN_AS_NODE: '1' },
    encoding: 'utf8',
    timeout: 20_000,
  });
  expect(control.stdout).toContain('NODE-MODE-ACTIVE'); // proves the hazard exists without the fuse

  // The installed build: same variable, same -e argument.
  const { env } = prepare(testInfo.outputPath('runasnode'));
  const port = await freePort();
  const child = spawn(
    exe!,
    [`--remote-debugging-port=${port}`, '-e', 'console.log("NODE-MODE-ACTIVE")'],
    {
      env: { ...cleanEnv(env), ELECTRON_RUN_AS_NODE: '1' },
      windowsHide: false,
    },
  );
  let out = '';
  child.stdout?.on('data', (d: Buffer) => (out += d.toString()));
  const browser = await attach(port);
  try {
    const page = await firstPage(browser);
    await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible({ timeout: 60_000 }); // opened the app
    expect(out).not.toContain('NODE-MODE-ACTIVE'); // did not run the script as Node
    expect(sidecarRunning()).toBe(true); // the real startup happened
  } finally {
    await browser.close().catch(() => undefined);
    closeGracefully(child);
    await expect.poll(sidecarRunning, { timeout: 20_000 }).toBe(false);
  }
});

// eslint-disable-next-line no-empty-pattern -- Playwright requires a destructuring pattern
test('the Node inspector and NODE_OPTIONS cannot be used against the installed app (fuses)', async ({}, testInfo) => {
  const { env } = prepare(testInfo.outputPath('inspect'));
  const child = track(exe!, ['--inspect=9339'], {
    env: { ...cleanEnv(env), NODE_OPTIONS: '--require C:\\does-not-exist.js' },
    windowsHide: false,
  });
  let err = '';
  child.stderr?.on('data', (d: Buffer) => (err += d.toString()));
  try {
    await new Promise((r) => setTimeout(r, 8000));
    // No inspector socket was opened, and the bad NODE_OPTIONS did not stop the app from starting.
    const listening = execSync('netstat -ano', { encoding: 'utf8' }).includes(':9339');
    expect(listening).toBe(false);
    expect(err).not.toContain('does-not-exist');
    expect(sidecarRunning()).toBe(true);
  } finally {
    closeGracefully(child);
    await expect.poll(sidecarRunning, { timeout: 20_000 }).toBe(false);
  }
});

// eslint-disable-next-line no-empty-pattern -- Playwright requires a destructuring pattern
test('the installed (fused) app still enforces the offline rules: CSP, no outside requests, minimal bridge', async ({}, testInfo) => {
  const { env } = prepare(testInfo.outputPath('offline'));
  const port = await freePort();
  track(exe!, [`--remote-debugging-port=${port}`], { env: cleanEnv(env), windowsHide: false });
  const browser = await attach(port);
  try {
    const page = await firstPage(browser);
    await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible({ timeout: 60_000 });
    const requested: string[] = [];
    browser.contexts()[0]!.on('request', (r) => requested.push(r.url()));

    const probe = await page.evaluate(async () => {
      const tryFetch = async (url: string) =>
        fetch(url, { mode: 'no-cors' }).then(
          () => 'reached',
          () => 'blocked',
        );
      const csp = (await fetch(`${window.pperp!.apiBase}/`)).headers.get('content-security-policy');
      return {
        outside: await tryFetch('https://example.com/'),
        http: await tryFetch('http://example.com/'),
        csp,
        bridge: Object.keys(window.pperp ?? {}).sort(),
        node: [
          typeof (window as unknown as { require?: unknown }).require,
          typeof (window as unknown as { process?: unknown }).process,
        ],
      };
    });
    expect(probe.outside).toBe('blocked');
    expect(probe.http).toBe('blocked');
    expect(probe.csp).toMatch(/^default-src 'self'/);
    expect(probe.bridge).toEqual(['apiBase', 'files', 'launchSecret', 'mode', 'print', 'shell']);
    expect(probe.node).toEqual(['undefined', 'undefined']);
  } finally {
    await browser.close().catch(() => undefined);
  }
});

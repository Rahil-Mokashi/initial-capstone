import { existsSync, statSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { desktopDir } from './global-setup';
import { expect, launchApp, signIn, test } from './fixtures';

test.describe('electron hardening', () => {
  test('the page has no Node, no require, and only the three bridge members', async ({
    launched,
  }) => {
    const { page } = launched;
    const probe = await page.evaluate(() => ({
      require: typeof (window as unknown as { require?: unknown }).require,
      process: typeof (window as unknown as { process?: unknown }).process,
      buffer: typeof (window as unknown as { Buffer?: unknown }).Buffer,
      bridge: Object.keys(window.pperp ?? {}).sort(),
      print: Object.keys((window.pperp as unknown as { print: object }).print).sort(),
    }));
    expect(probe.require).toBe('undefined');
    expect(probe.process).toBe('undefined');
    expect(probe.buffer).toBe('undefined');
    expect(probe.bridge).toEqual(['apiBase', 'files', 'launchSecret', 'print']);
    expect(probe.print).toEqual(['listPrinters', 'preview', 'toPdf', 'toPrinter']);
  });

  test('web preferences are locked down', async ({ launched }) => {
    const { app } = launched;
    const prefs = await app.evaluate(({ BrowserWindow }) => {
      const p = (
        BrowserWindow.getAllWindows()[0]!.webContents as unknown as {
          getLastWebPreferences(): Record<string, unknown>;
        }
      ).getLastWebPreferences();
      return { ci: p.contextIsolation, ni: p.nodeIntegration, sb: p.sandbox, wv: p.webviewTag };
    });
    expect(prefs).toEqual({ ci: true, ni: false, sb: true, wv: false });
  });

  test('new windows are denied and navigating away from the app is blocked', async ({
    launched,
  }) => {
    const { page, app } = launched;
    const before = page.url();
    await page.evaluate(() => window.open('https://example.com/', '_blank'));
    await page.evaluate(() => {
      location.href = 'https://example.com/';
    });
    await page.waitForTimeout(800);
    expect(app.windows()).toHaveLength(1);
    expect(page.url()).toBe(before);
  });

  test('the UI is served with a strict CSP and the API demands the launch secret', async ({
    launched,
  }) => {
    const { page } = launched;
    const probe = await page.evaluate(async () => {
      const base = window.pperp!.apiBase;
      const noSecret = await fetch(`${base}/api/tanks`);
      const page = await fetch(`${base}/`);
      return { noSecret: noSecret.status, csp: page.headers.get('content-security-policy') };
    });
    expect(probe.noSecret).toBe(403);
    expect(probe.csp).toMatch(/^default-src 'self'/);
  });

  test('a second launch does not start a second app (single-instance lock)', async ({
    launched,
  }) => {
    const { app, userData, dbPath } = launched;
    const electronPath = (await import('electron')).default as unknown as string;
    const env = {
      ...process.env,
      PPERP_USER_DATA: userData,
      PETROL_PUMP_DB_PATH: dbPath,
      PPERP_E2E: '1',
    };
    delete (env as Record<string, string | undefined>).ELECTRON_RUN_AS_NODE;
    const second = spawn(electronPath, [desktopDir], { env, stdio: 'ignore', windowsHide: true });
    const code = await new Promise<number | null>((resolve) => second.once('exit', resolve));
    expect(code).toBe(0);
    expect(app.windows()).toHaveLength(1);
  });
});

test.describe('process lifecycle', () => {
  test('quitting asks the API to stop first, so the database is checkpointed', async ({
    launched,
  }, testInfo) => {
    const { app, page, dbPath } = launched;
    await signIn(page, 'manager1');
    await expect(page.getByRole('heading', { name: 'T1' })).toBeVisible();
    // A write leaves data in the WAL file while the app is running.
    await page
      .getByRole('listitem')
      .filter({ has: page.getByRole('heading', { name: 'T1' }) })
      .getByRole('button', { name: 'Receipt' })
      .click();
    await page.getByLabel('Quantity (L)').fill('5');
    await page.getByRole('button', { name: 'Record receipt' }).click();
    await expect(page.getByRole('status')).toContainText('Receipt recorded');
    await expect
      .poll(() => existsSync(`${dbPath}-wal`) && statSync(`${dbPath}-wal`).size > 0)
      .toBe(true);

    await app.close();
    // Graceful shutdown folds the WAL back into the database and removes it.
    await expect
      .poll(() => (existsSync(`${dbPath}-wal`) ? statSync(`${dbPath}-wal`).size : 0), {
        timeout: 20_000,
      })
      .toBe(0);
    testInfo.annotations.push({ type: 'note', description: 'WAL checkpointed on quit' });
  });

  test('if the service crashes the user sees a clear error with Try again, then recovers', async ({
    launched,
  }) => {
    const { app, page } = launched;
    await signIn(page, 'manager1');
    await expect(page.getByRole('heading', { name: 'T1' })).toBeVisible();

    const pid = await app.evaluate(() =>
      (globalThis as { __pperp?: { getSidecarPid(): number } }).__pperp!.getSidecarPid(),
    );
    expect(pid).toBeGreaterThan(0);
    // Kill the whole service process tree the hard way, as a crash would.
    spawn('taskkill', ['/pid', String(pid), '/T', '/F'], { windowsHide: true });

    const findWindow = (part: string) => app.windows().find((w) => w.url().includes(part));
    await expect.poll(() => Boolean(findWindow('error.html')), { timeout: 30_000 }).toBe(true);
    const errorPage = findWindow('error.html')!;
    await expect(
      errorPage.getByRole('heading', { name: 'The application could not start' }),
    ).toBeVisible();
    await expect(errorPage.getByText('stopped unexpectedly')).toBeVisible();

    await errorPage.getByRole('button', { name: 'Try again' }).click();
    await expect
      .poll(() => Boolean(findWindow('http://127.0.0.1')), { timeout: 60_000 })
      .toBe(true);
    const fresh = findWindow('http://127.0.0.1')!;
    await expect(fresh.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  });

  // eslint-disable-next-line no-empty-pattern -- Playwright requires a destructuring pattern
  test('a service that cannot start shows the error screen, never a blank window', async ({}, testInfo) => {
    const broken = await launchApp(testInfo.outputPath('broken'), {
      // A directory where the database file should be: SQLite cannot open it.
      dbPath: testInfo.outputPath('broken'),
    });
    try {
      await expect(
        broken.page.getByRole('heading', { name: 'The application could not start' }),
      ).toBeVisible({ timeout: 90_000 });
      await expect(broken.page.getByRole('button', { name: 'Try again' })).toBeVisible();
    } finally {
      await broken.app.close().catch(() => undefined);
    }
  });
});

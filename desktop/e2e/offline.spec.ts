import { expect, signIn, test } from './fixtures';

/** Hosts a request may legitimately touch. Anything else means the app tried to leave this PC. */
function outsideLoopback(urls: string[]): string[] {
  return urls.filter((u) => {
    try {
      const url = new URL(u);
      if (url.protocol === 'file:' || url.protocol === 'devtools:') return false; // the app's own files
      return url.hostname !== '127.0.0.1';
    } catch {
      return true;
    }
  });
}

test.describe('offline proof', () => {
  test('a full session (login, tanks, a write, logout) never requests anything outside 127.0.0.1', async ({
    launched,
  }) => {
    const { page, app, requested } = launched;
    await signIn(page, 'manager1');
    const t1 = page
      .getByRole('listitem')
      .filter({ has: page.getByRole('heading', { name: 'T1' }) });
    await t1.getByRole('button', { name: 'Receipt' }).click();
    await page.getByLabel('Quantity (L)').fill('10');
    await page.getByRole('button', { name: 'Record receipt' }).click();
    await expect(page.getByRole('status')).toContainText('Receipt recorded');
    await page.getByRole('button', { name: 'Table' }).click();
    await page.getByRole('link', { name: 'T1' }).click();
    await page.getByRole('tab', { name: 'Readings' }).click();
    await page.getByRole('button', { name: 'Log out' }).click();
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();

    expect(requested.length).toBeGreaterThan(5);
    // FAILS the test if the app ever attempted a request outside this PC - blocked or not.
    expect(outsideLoopback(requested), 'requests leaving 127.0.0.1').toEqual([]);

    // The main-process blocker had nothing to cancel during normal use.
    const blocked = await app.evaluate(
      () => (globalThis as { __pperp?: { blocked: string[] } }).__pperp?.blocked ?? ['<no hook>'],
    );
    expect(blocked).toEqual([]);
  });

  test('layer 1 - the page CSP stops a request to the internet before it leaves the page', async ({
    launched,
  }) => {
    const { page } = launched;
    const outcome = await page.evaluate(async () => {
      try {
        await fetch('https://example.com/', { mode: 'no-cors' });
        return 'reached';
      } catch (e) {
        return `failed: ${(e as Error).name}`;
      }
    });
    expect(outcome).toMatch(/^failed/);
  });

  test('layer 2 - even with NO CSP at all, the main-process blocker cancels requests to the internet', async ({
    launched,
  }) => {
    const { app } = launched;
    // A window with no Content-Security-Policy: only the session-level blocker stands in the way.
    const results = await app.evaluate(async ({ BrowserWindow }) => {
      const win = new BrowserWindow({ show: false, webPreferences: { sandbox: true } });
      await win.loadURL('about:blank');
      const attempt = (url: string) =>
        win.webContents.executeJavaScript(
          `fetch(${JSON.stringify(url)}, { mode: 'no-cors' }).then(() => 'reached', () => 'blocked')`,
        );
      const out: Record<string, string> = {};
      for (const url of [
        'https://example.com/',
        'http://example.com/',
        'http://192.168.1.1/',
        'http://localhost:9/',
        'ftp://example.com/x',
      ]) {
        out[url] = (await attempt(url)) as string;
      }
      out.websocket = (await win.webContents.executeJavaScript(
        `new Promise((r) => { const w = new WebSocket('wss://example.com/s'); w.onopen = () => r('reached'); w.onerror = () => r('blocked'); })`,
      )) as string;
      win.destroy();
      return out;
    });
    expect(
      Object.values(results).every((v) => v === 'blocked'),
      JSON.stringify(results),
    ).toBe(true);
    const blocked = await app.evaluate(
      () => (globalThis as { __pperp?: { blocked: string[] } }).__pperp?.blocked ?? [],
    );
    for (const url of [
      'https://example.com/',
      'http://example.com/',
      'http://192.168.1.1/',
      'wss://example.com/s',
    ]) {
      expect(blocked, `blocker log should contain ${url}`).toContain(url);
    }
  });

  test('the main process itself is blocked from leaving too (session-level, not page-level)', async ({
    launched,
  }) => {
    const { app } = launched;
    const result = await app.evaluate(async ({ session }) => {
      try {
        await session.defaultSession.fetch('https://example.com/');
        return 'reached';
      } catch {
        return 'blocked';
      }
    });
    expect(result).toBe('blocked');
    const blocked = await app.evaluate(
      () => (globalThis as { __pperp?: { blocked: string[] } }).__pperp?.blocked ?? [],
    );
    expect(blocked).toContain('https://example.com/');
  });

  test('a script injected from outside cannot load: the CSP refuses it before the network is touched', async ({
    launched,
  }) => {
    const { page } = launched;
    const loaded = await page.evaluate(
      () =>
        new Promise<string>((resolve) => {
          const s = document.createElement('script');
          s.src = 'https://cdn.example.com/evil.js';
          s.onload = () => resolve('loaded');
          s.onerror = () => resolve('refused');
          document.head.appendChild(s);
        }),
    );
    expect(loaded).toBe('refused');
    // Inline script text is refused too (no 'unsafe-inline'); the browser reports the violation.
    const violation = await page.evaluate(
      () =>
        new Promise<string>((resolve) => {
          document.addEventListener(
            'securitypolicyviolation',
            (e) => resolve(e.violatedDirective),
            { once: true },
          );
          const s = document.createElement('script');
          s.textContent = 'window.__injected = true';
          document.head.appendChild(s);
          setTimeout(() => resolve('no violation'), 2000);
        }),
    );
    expect(violation).toMatch(/^script-src/);
    expect(
      await page.evaluate(() => (window as unknown as { __injected?: boolean }).__injected),
    ).toBeUndefined();
  });
});

import { expect, test } from '@playwright/test';
import { execSync } from 'node:child_process';
import { attach, cleanEnv, firstPage, freePort, prepare, track } from './installed';

// The installed app, placed in a DELIBERATELY deep folder, must explain the problem instead of crashing.
// Opt-in: npm run test:deep-path (installs into a deep folder itself), or set PPERP_DEEP_EXE to an
// installation whose folder is longer than ~130 characters.
const exe = process.env.PPERP_DEEP_EXE;
test.skip(!exe, 'set PPERP_DEEP_EXE (or run npm run test:deep-path)');

// eslint-disable-next-line no-empty-pattern -- Playwright requires a destructuring pattern
test('a too-long install path shows a clear message and does not start the service', async ({}, testInfo) => {
  const { env } = prepare(testInfo.outputPath('deep'));
  const port = await freePort();
  track(exe!, [`--remote-debugging-port=${port}`], { env: cleanEnv(env), windowsHide: false });
  const browser = await attach(port);
  try {
    const page = await firstPage(browser);
    await expect(
      page.getByRole('heading', { name: 'The application could not start' }),
    ).toBeVisible();
    const text = await page.locator('#details').innerText();
    expect(text).toContain('installed in a folder whose path is too long');
    expect(text).toContain('C:\\PPERP');
    expect(text).toMatch(/at most \d+ characters/);
    const running = execSync('tasklist /FI "IMAGENAME eq pperp-api.exe" /NH', { encoding: 'utf8' });
    expect(running).not.toContain('pperp-api.exe');
  } finally {
    await browser.close().catch(() => undefined);
  }
});

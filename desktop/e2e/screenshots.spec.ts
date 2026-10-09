import { resolve } from 'node:path';
import { expect, signIn, test } from './fixtures';

// Only runs when asked: SCREENSHOTS=1 npx playwright test e2e/screenshots.spec.ts
// Writes real screenshots of the running app into docs/.
test.skip(process.env.SCREENSHOTS !== '1', 'screenshots are generated on demand');

const docs = resolve(__dirname, '..', '..', 'docs');

test('capture login and tanks screens', async ({ launched }) => {
  const { page } = launched;
  await page.setViewportSize({ width: 1360, height: 860 });
  await page.screenshot({ path: resolve(docs, 'js-login.png') });

  await signIn(page, 'manager1');
  await expect(page.getByRole('heading', { name: 'T1' })).toBeVisible();
  await page.screenshot({ path: resolve(docs, 'js-tanks.png') });

  await page.getByRole('link', { name: 'Open' }).first().click();
  await expect(page.getByRole('heading', { name: 'Tank T1' })).toBeVisible();
  await expect(page.getByText('No transactions for this tank yet')).toBeVisible();
  await page.screenshot({ path: resolve(docs, 'js-tank-detail.png') });

  await page.getByRole('link', { name: 'All tanks' }).click();
  await page.getByRole('button', { name: 'Switch to dark theme' }).click();
  await expect(page.getByRole('heading', { name: 'T1' })).toBeVisible();
  await page.waitForTimeout(600); // let the colour transition finish
  await page.screenshot({ path: resolve(docs, 'js-tanks-dark.png') });
});

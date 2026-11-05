import { resolve } from 'node:path';
import { expect, signIn, test } from './fixtures';

// Only runs when asked: SCREENSHOTS=1 npx playwright test e2e/screenshots.spec.ts
// Writes real screenshots of the running app into docs/.
test.skip(process.env.SCREENSHOTS !== '1', 'screenshots are generated on demand');

const docs = resolve(__dirname, '..', '..', 'docs');

test('capture login and tanks screens', async ({ launched }) => {
  const { page } = launched;
  await page.setViewportSize({ width: 1360, height: 860 });
  await page.screenshot({ path: resolve(docs, 'migration/img/js-login.png') });

  await signIn(page, 'manager1');
  await expect(page.getByRole('heading', { name: 'T1' })).toBeVisible();
  await page.screenshot({ path: resolve(docs, 'migration/img/js-tanks.png') });

  await page.getByRole('link', { name: 'Open' }).first().click();
  await expect(page.getByRole('heading', { name: 'Tank T1' })).toBeVisible();
  await expect(page.getByText('No transactions for this tank yet')).toBeVisible();
  await page.screenshot({ path: resolve(docs, 'migration/img/js-tank-detail.png') });

  await page.getByRole('link', { name: 'All tanks' }).click();
  await page.getByRole('button', { name: 'Switch to dark theme' }).click();
  await expect(page.getByRole('heading', { name: 'T1' })).toBeVisible();
  await page.waitForTimeout(600); // let the colour transition finish
  await page.screenshot({ path: resolve(docs, 'migration/img/js-tanks-dark.png') });
});

test('capture the variance bars (warning, critical, dark)', async ({ launched }) => {
  const { page } = launched;
  await page.setViewportSize({ width: 1360, height: 860 });
  await signIn(page, 'manager1');
  const reconcile = async (tank: string, physical: string) => {
    await page
      .getByRole('link', { name: 'All tanks' })
      .click()
      .catch(() => undefined);
    const card = page
      .getByRole('listitem')
      .filter({ has: page.getByRole('heading', { name: tank }) });
    await card.getByRole('link', { name: 'Open' }).click();
    await page.getByRole('button', { name: 'Reconcile', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: new RegExp(`Reconcile - ${tank}`) });
    await dialog.getByLabel('Physical stock (L)').fill(physical);
    await dialog.getByRole('button', { name: 'Reconcile' }).click();
    await page.getByRole('button', { name: 'Done' }).click();
    await page.getByRole('tab', { name: 'Reconciliation' }).click();
    await expect(page.getByRole('figure')).toBeVisible();
  };
  // T1: expected 2,500.500, physical 2,480.000 -> -0.82 % -> "warning" (amber)
  await reconcile('T1', '2480.000');
  await page.screenshot({ path: resolve(docs, 'migration/img/js-variance-warning.png') });
  // T2: expected 1,800.000, physical 1,700.000 -> -5.56 % -> "approval_required" (red)
  await reconcile('T2', '1700.000');
  await page.screenshot({ path: resolve(docs, 'migration/img/js-variance-critical.png') });
  await page.getByRole('button', { name: 'Switch to dark theme' }).click();
  await page.waitForTimeout(600);
  await page.screenshot({ path: resolve(docs, 'migration/img/js-variance-critical-dark.png') });
});

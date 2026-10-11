import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { expect, signIn, test, setupPump } from './fixtures';

test('record a sale, see the stock fall, open the receipt preview and save the receipt PDF', async ({
  launched,
}, testInfo) => {
  const { page, app } = launched;
  await signIn(page, 'manager1');
  await expect(page.getByRole('heading', { level: 1, name: /Tanks/ })).toBeVisible();
  await setupPump(page);
  const saveDir = testInfo.outputPath('saved');
  await app.evaluate((_e, dir) => {
    process.env.PPERP_E2E_SAVE_DIR = dir as string;
  }, saveDir);

  await page.getByRole('link', { name: 'Sales', exact: true }).click();
  await page.getByRole('button', { name: /Record sale/ }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Shift').selectOption({ index: 1 });
  await dialog.getByLabel('Nozzle').selectOption({ index: 1 });
  await dialog.getByLabel('Attendant').selectOption({ index: 1 });
  await dialog.getByLabel('Quantity (L)').fill('');
  await dialog.getByLabel('Quantity (L)').pressSequentially('12.5');
  await dialog.getByRole('button', { name: 'Record sale' }).click();
  await expect(dialog).toBeHidden();

  const row = page.getByRole('row').filter({ hasText: 'Petrol' });
  await expect(row).toContainText('12.500');
  await expect(row).toContainText('₹1,250.00');
  await expect(page.getByRole('list', { name: "Today's revenue by fuel" })).toContainText('₹1,250.00');

  await row.getByRole('radio').check();
  const previewPromise = app.waitForEvent('window');
  await page.getByRole('button', { name: 'Print receipt' }).click();
  const preview = await previewPromise;
  await expect(preview).toHaveTitle('Print preview');
  await expect(preview.locator('#doc')).toBeVisible();
  const body = preview.frameLocator('#doc').locator('body');
  await expect(body).toContainText('Receipt');
  await expect(body).toContainText('1250.00');
  await preview.getByRole('button', { name: 'Close' }).click();

  await page.getByRole('button', { name: 'Export PDF' }).click();
  await expect(page.getByText(/Saved to /)).toBeVisible();
  const saved = join(saveDir, readSavedName(saveDir));
  expect(existsSync(saved)).toBe(true);
  expect(readFileSync(saved).subarray(0, 4).toString()).toBe('%PDF');

  await page.getByRole('link', { name: 'Tanks' }).click();
  await expect(
    page.getByRole('listitem').filter({ has: page.getByRole('heading', { name: 'T1' }) }),
  ).toContainText('2,488.000');
});

function readSavedName(dir: string): string {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const names = (require('node:fs') as typeof import('node:fs')).readdirSync(dir);
  return names.find((n) => n.endsWith('.pdf'))!;
}

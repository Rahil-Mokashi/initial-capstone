import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { expect, setupPump, signIn, test } from './fixtures';

test('open the sales report, filter by date, preview it and save PDF, Excel and CSV', async ({
  launched,
}, testInfo) => {
  const { page, app } = launched;
  await signIn(page, 'manager1');
  await expect(page.getByRole('heading', { level: 1, name: /Tanks/ })).toBeVisible();
  const pump = await setupPump(page);
  await pump.api('POST', '/terminal/sales', {
    mode: 'amount',
    value: '1000.00',
    payment_method: 'cash',
    shift_id: pump.shiftId,
    nozzle_id: pump.nozzleId,
    employee_id: pump.employeeId,
  });
  const saveDir = testInfo.outputPath('saved');
  await app.evaluate((_e, dir) => {
    process.env.PPERP_E2E_SAVE_DIR = dir as string;
  }, saveDir);

  await page.getByRole('link', { name: 'Reports' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Reports' })).toBeVisible();
  await page.getByRole('link', { name: 'Sales Report' }).click();
  const table = page.getByRole('table', { name: 'Sales Report' });
  await expect(table).toContainText('Petrol');
  await expect(table).toContainText('1,000.00');

  // A window with no sales gives a zero total
  await page.getByLabel('From', { exact: true }).fill('2000-01-01');
  await page.getByLabel('To', { exact: true }).fill('2000-01-02');
  await page.getByRole('button', { name: /Refresh/ }).click();
  await expect(table.getByRole('row').last()).toContainText('0.00');

  // Back to everything, then print preview + all three exports
  await page.getByLabel('From', { exact: true }).fill('');
  await page.getByLabel('To', { exact: true }).fill('');
  await page.getByRole('button', { name: /Refresh/ }).click();
  await expect(table).toContainText('1,000.00');

  const previewPromise = app.waitForEvent('window');
  await page.getByRole('button', { name: 'Print', exact: true }).click();
  const preview = await previewPromise;
  const doc = preview.frameLocator('#doc').locator('body');
  await expect(doc).toContainText('Sales Report');
  await expect(doc).toContainText('1000.00');
  await preview.getByRole('button', { name: 'Close' }).click();

  let saved = 0;
  for (const label of ['Export PDF', 'Export Excel', 'Export CSV']) {
    await page.getByRole('button', { name: label }).click();
    saved += 1;
    await expect(page.getByText(/Saved to /)).toHaveCount(saved);
  }
  const files = readdirSync(saveDir).sort();
  expect(files).toEqual(['sales_report.csv', 'sales_report.pdf', 'sales_report.xlsx']);
  expect(readFileSync(join(saveDir, 'sales_report.pdf')).subarray(0, 4).toString()).toBe('%PDF');
  expect(readFileSync(join(saveDir, 'sales_report.xlsx')).subarray(0, 2).toString()).toBe('PK');
  expect(readFileSync(join(saveDir, 'sales_report.csv'), 'utf8')).toContain('1000.00');
});

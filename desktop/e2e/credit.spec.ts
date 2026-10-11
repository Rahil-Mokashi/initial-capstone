import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { expect, setupPump, signIn, test } from './fixtures';

test('credit account: sell on credit, pay part, read the statement, export PDF and Excel', async ({
  launched,
}, testInfo) => {
  const { page, app } = launched;
  await signIn(page, 'manager1');
  await expect(page.getByRole('heading', { level: 1, name: /Tanks/ })).toBeVisible();
  const pump = await setupPump(page);
  await pump.api('POST', '/customers', { name: 'ACME Transport' });
  const saveDir = testInfo.outputPath('saved');
  await app.evaluate((_e, dir) => {
    process.env.PPERP_E2E_SAVE_DIR = dir as string;
  }, saveDir);

  await page.getByRole('link', { name: 'Credit', exact: true }).click();
  await page.getByRole('button', { name: /Open credit account/ }).click();
  let dialog = page.getByRole('dialog');
  await dialog.getByLabel('Customer').selectOption({ label: 'ACME Transport' });
  await dialog.getByLabel('Credit limit').fill('');
  await dialog.getByLabel('Credit limit').pressSequentially('5000');
  await dialog.getByRole('button', { name: 'Open account' }).click();
  await expect(page.getByRole('row', { name: /ACME Transport/ })).toContainText('₹5,000.00');

  // A credit sale through the Terminal, as an attendant would do it
  await page.getByRole('link', { name: 'Terminal' }).click();
  await page.getByRole('button', { name: 'Credit' }).click();
  await page.getByLabel('Customer (required for credit)').selectOption({ label: 'ACME Transport' });
  await page.getByLabel('Amount (₹)').fill('');
  await page.getByLabel('Amount (₹)').pressSequentially('1500');
  await page.getByRole('button', { name: 'Complete sale' }).click();
  await expect(page.getByRole('heading', { name: 'Sale recorded' })).toBeVisible();
  await page.getByRole('link', { name: 'Credit', exact: true }).click();
  await expect(page.getByRole('row', { name: /ACME Transport/ })).toContainText('₹1,500.00');

  await page.getByRole('radio', { name: 'Select ACME Transport' }).check();
  await page.getByRole('button', { name: 'Record payment' }).click();
  dialog = page.getByRole('dialog');
  await dialog.getByLabel('Amount').fill('');
  await dialog.getByLabel('Amount').pressSequentially('500');
  await dialog.getByRole('button', { name: 'Record payment' }).click();
  await expect(page.getByRole('row', { name: /ACME Transport/ })).toContainText('₹1,000.00');

  await page.getByRole('button', { name: 'View statement' }).click();
  dialog = page.getByRole('dialog');
  await expect(dialog.getByText('Running balance: ₹1,000.00')).toBeVisible();
  await dialog.getByRole('button', { name: 'Export PDF' }).click();
  await expect(page.getByText(/Saved to .*customer_statement\.pdf/)).toBeVisible();
  await dialog.getByRole('button', { name: 'Export Excel' }).click();
  await expect(page.getByText(/Saved to .*customer_statement\.xlsx/)).toBeVisible();
  const files = readdirSync(saveDir);
  expect(files.sort()).toEqual(['customer_statement.pdf', 'customer_statement.xlsx']);
  expect(existsSync(join(saveDir, 'customer_statement.pdf'))).toBe(true);
  expect(readFileSync(join(saveDir, 'customer_statement.pdf')).subarray(0, 4).toString()).toBe('%PDF');
  expect(readFileSync(join(saveDir, 'customer_statement.xlsx')).subarray(0, 2).toString()).toBe('PK');
});

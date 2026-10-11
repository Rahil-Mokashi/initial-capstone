import { expect, signIn, test } from './fixtures';

test('a manager adds a dispenser and a nozzle, then puts the nozzle in maintenance', async ({
  launched,
}) => {
  const { page } = launched;
  await signIn(page, 'manager1');
  await page.getByRole('link', { name: 'Nozzles & Dispensers' }).click();

  await page.getByRole('button', { name: /Add dispenser/ }).click();
  await page.getByRole('dialog').getByLabel('Code').fill('D1');
  await page.getByRole('dialog').getByRole('button', { name: 'Save' }).click();
  await expect(page.getByRole('cell', { name: 'D1', exact: true })).toBeVisible();

  await page.getByRole('tab', { name: 'Nozzles' }).click();
  await page.getByRole('button', { name: /Add nozzle/ }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Code').fill('N1');
  await dialog.getByLabel('Dispenser').selectOption({ label: 'D1' });
  await dialog.getByLabel('Fuel type').selectOption({ label: 'Petrol' });
  await dialog.getByLabel('Tank').selectOption({ index: 1 });
  await dialog.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByRole('row', { name: /N1/ })).toContainText('Petrol');

  await page.getByRole('button', { name: 'Change status - nozzle N1' }).click();
  await page.getByRole('dialog').getByLabel('New status').selectOption('maintenance');
  await page.getByRole('dialog').getByRole('button', { name: 'Change status' }).click();
  await expect(page.getByRole('row', { name: /N1/ })).toContainText('Maintenance');
});

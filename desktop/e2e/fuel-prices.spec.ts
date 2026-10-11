import { expect, signIn, test } from './fixtures';

test('a manager prices a fuel with a reason and sees it in the history', async ({ launched }) => {
  const { page } = launched;
  await signIn(page, 'manager1');
  await page.getByRole('link', { name: 'Fuel Prices' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Fuel Prices' })).toBeVisible();

  await page.getByRole('button', { name: /Change price of Petrol/ }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('New rate per litre').fill('');
  await dialog.getByLabel('New rate per litre').pressSequentially('104.505');
  await expect(dialog.getByLabel('New rate per litre')).toHaveValue('104.50');
  await dialog.getByLabel('Reason').fill('OMC revision');
  await dialog.getByRole('button', { name: 'Save' }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole('row', { name: /Petrol/ })).toContainText('₹104.50');

  await page.getByRole('button', { name: 'Price history for Petrol' }).click();
  await expect(page.getByRole('dialog')).toContainText('OMC revision');
});

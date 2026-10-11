import { expect, signIn, test } from './fixtures';

test('add a category, record an expense, then approve it', async ({ launched }) => {
  const { page } = launched;
  await signIn(page, 'manager1');
  await page.getByRole('link', { name: 'Expenses' }).click();

  await page.getByRole('tab', { name: 'Categories' }).click();
  await page.getByRole('button', { name: /Add category/ }).click();
  await page.getByRole('dialog').getByLabel('Name').fill('Tea and snacks');
  await page.getByRole('dialog').getByRole('button', { name: 'Save' }).click();
  await expect(page.getByRole('cell', { name: 'Tea and snacks' })).toBeVisible();

  await page.getByRole('tab', { name: 'Expenses' }).click();
  await page.getByRole('button', { name: /Record expense/ }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Category').selectOption({ label: 'Tea and snacks' });
  await dialog.getByLabel('Employee').selectOption({ index: 1 });
  await dialog.getByRole('button', { name: 'Record expense' }).click();
  await expect(dialog).toBeHidden();
  const row = page.getByRole('row').filter({ hasText: 'Tea and snacks' });
  await expect(row).toContainText('₹500.00');
  await expect(row).toContainText('Pending');

  await row.getByRole('radio').check();
  await page.getByRole('button', { name: 'Approve selected' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Approve' }).click();
  await expect(row).toContainText('Approved');
});

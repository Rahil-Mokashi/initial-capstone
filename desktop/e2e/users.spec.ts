import { expect, signIn, test } from './fixtures';

test('an admin adds a user, deactivates them with no reason typed', async ({
  launched,
}) => {
  const { page } = launched;
  await signIn(page, 'admin1');
  await page.getByRole('link', { name: 'Users' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Users' })).toBeVisible();

  await page.getByRole('button', { name: /Add user/ }).click();
  const dialog = page.getByRole('dialog', { name: 'Add user' });
  await dialog.getByLabel('Username').fill('newbie');
  await dialog.getByLabel('Email').fill('newbie@example.com');
  await dialog.getByLabel('Password').fill('Str0ngPass!x');
  await dialog.getByLabel('Role').selectOption({ label: 'ATTENDANT' });
  await dialog.getByRole('button', { name: 'Save' }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole('row', { name: /newbie/ })).toContainText('Active');

  await page.getByRole('link', { name: 'Open newbie' }).click();
  await page.getByRole('button', { name: 'Deactivate' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Deactivate' }).click();
  await expect(page.getByText('Inactive')).toBeVisible();
});

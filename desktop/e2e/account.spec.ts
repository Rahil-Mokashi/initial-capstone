import { apiAs, expect, PASSWORD, signIn, test } from './fixtures';

test('dashboard, set a PIN, lock and unlock, sign in with the PIN', async ({ launched }) => {
  const { page } = launched;
  await signIn(page, 'manager1', PASSWORD, { home: true });
  await expect(page.getByRole('heading', { level: 1, name: /Good (morning|afternoon|evening), Manager1/ })).toBeVisible();
  await expect(page.getByText('Live tank levels')).toBeVisible();
  await expect(page.getByText(/Offline — Local Only/)).toBeVisible();

  // Set a quick sign-in PIN
  await page.getByRole('button', { name: /Account menu/ }).click();
  await page.getByRole('button', { name: 'Set a quick sign-in PIN' }).click();
  let dialog = page.getByRole('dialog');
  await dialog.getByLabel('Current password').fill(PASSWORD);
  await dialog.getByLabel('New PIN').fill('483920');
  await dialog.getByLabel('Confirm PIN').fill('483920');
  await dialog.getByRole('button', { name: 'Set PIN' }).click();
  await expect(dialog).toBeHidden();

  // Lock: wrong password is refused, the right one resumes the same session
  await page.getByRole('button', { name: /Account menu/ }).click();
  await page.getByRole('button', { name: 'Lock' }).click();
  const lock = page.getByRole('dialog', { name: /Welcome back/ });
  await lock.getByLabel('Password').fill('not-it');
  await lock.getByRole('button', { name: 'Unlock' }).click();
  await expect(lock.getByRole('alert')).toBeVisible();
  await lock.getByRole('button', { name: 'Use PIN instead' }).click();
  await lock.getByLabel('PIN').fill('483920');
  await lock.getByRole('button', { name: 'Unlock' }).click();
  await expect(lock).toBeHidden();
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();

  // Log out, then sign in with the PIN
  await page.getByRole('button', { name: /Account menu/ }).click();
  await page.getByRole('button', { name: 'Log out' }).click();
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  await page.getByRole('button', { name: 'Use PIN instead' }).click();
  await page.getByLabel('Username').fill('manager1');
  await page.getByLabel('PIN').fill('483920');
  await page.getByRole('button', { name: /^Sign in/i }).click();
  await expect(page.getByRole('heading', { level: 1, name: /Good/ })).toBeVisible();
});

test('forgot password: an admin code lets the person sign in with a new password', async ({ launched }) => {
  const { page } = launched;
  await signIn(page, 'admin1', PASSWORD, { home: true });
  await expect(page.getByRole('heading', { level: 1, name: /Good/ })).toBeVisible();
  const api = await apiAs(page, 'admin1');
  const users = (await api('GET', '/users')) as unknown as Array<{ id: string; username: string }>;
  const target = users.find((u) => u.username === 'attendant1')!;
  const { code } = (await api('POST', `/users/${target.id}/reset-code`, {})) as { code: string };
  await page.getByRole('button', { name: /Account menu/ }).click();
  await page.getByRole('button', { name: 'Log out' }).click();

  await page.getByRole('button', { name: 'Forgot password?' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Username').fill('attendant1');
  await dialog.getByLabel('Reset code').fill(code);
  await dialog.getByLabel('New password', { exact: true }).fill('N3w!Passw0rd');
  await dialog.getByLabel('Confirm new password').fill('N3w!Passw0rd');
  await dialog.getByRole('button', { name: 'Reset password' }).click();
  await expect(dialog).toBeHidden();

  await page.getByLabel('Username').fill('attendant1');
  await page.getByLabel('Password', { exact: true }).fill('N3w!Passw0rd');
  await page.getByRole('button', { name: /^Sign in/i }).click();
  await expect(page.getByRole('heading', { level: 1, name: /Good/ })).toBeVisible();
});

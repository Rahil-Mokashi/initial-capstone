import { expect, signIn, test } from './fixtures';

test('mark attendance, correct it, then an approved leave writes its days into attendance', async ({
  launched,
}) => {
  const { page } = launched;
  await signIn(page, 'manager1');

  await page.getByRole('link', { name: 'Attendance' }).click();
  const row = page.getByRole('row', { name: /Ravi Kumar/ });
  await row.getByRole('button', { name: 'Mark Ravi Kumar present' }).click();
  await expect(row).toContainText('Present');

  await page.getByRole('button', { name: 'Correct attendance of Ravi Kumar' }).click();
  await page.getByRole('dialog').getByLabel('Status').selectOption('late');
  await page.getByRole('dialog').getByRole('button', { name: 'Save correction' }).click();
  await expect(row).toContainText('Late');
  await expect(row).toContainText('Yes'); // corrected

  // Leave for tomorrow
  await page.getByRole('link', { name: 'Leave' }).click();
  await page.getByRole('button', { name: /Request leave/ }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Employee').selectOption({ index: 1 });
  const tomorrow = new Date(Date.now() + 24 * 3600 * 1000);
  const iso = `${tomorrow.getFullYear()}-${String(tomorrow.getMonth() + 1).padStart(2, '0')}-${String(tomorrow.getDate()).padStart(2, '0')}`;
  await dialog.getByLabel('From').fill(iso);
  await dialog.getByLabel('To').fill(iso);
  await dialog.getByLabel(/^Reason/).fill('family function');
  await dialog.getByRole('button', { name: 'Request leave' }).click();
  await expect(page.getByRole('row', { name: /Ravi Kumar/ })).toContainText('Pending');
  await page.getByRole('button', { name: 'Approve leave of Ravi Kumar' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Approve' }).click();
  await expect(page.getByRole('row', { name: /Ravi Kumar/ })).toContainText('Approved');

  await page.getByRole('link', { name: 'Attendance' }).click();
  await page.getByLabel('Date').fill(iso);
  await expect(page.getByRole('row', { name: /Ravi Kumar/ })).toContainText('Leave');
});

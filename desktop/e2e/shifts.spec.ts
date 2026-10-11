import { expect, signIn, test } from './fixtures';

test('open a shift, assign a nozzle, complete it with a meter reading, close and reopen the shift', async ({
  launched,
}) => {
  const { page } = launched;
  await signIn(page, 'manager1');

  // Set-up a real pump would already have: a priced fuel and a nozzle.
  await page.getByRole('link', { name: 'Fuel Prices' }).click();
  await page.getByRole('button', { name: /Change price of Petrol/ }).click();
  await page.getByRole('dialog').getByLabel('New rate per litre').fill('');
  await page.getByRole('dialog').getByLabel('New rate per litre').pressSequentially('100');
  await page.getByRole('dialog').getByRole('button', { name: 'Save' }).click();
  await expect(page.getByRole('row', { name: /Petrol/ })).toContainText('₹100');

  await page.getByRole('link', { name: 'Nozzles & Dispensers' }).click();
  await page.getByRole('button', { name: /Add dispenser/ }).click();
  await page.getByRole('dialog').getByLabel('Code').fill('D1');
  await page.getByRole('dialog').getByRole('button', { name: 'Save' }).click();
  await page.getByRole('tab', { name: 'Nozzles' }).click();
  await page.getByRole('button', { name: /Add nozzle/ }).click();
  const nozzle = page.getByRole('dialog');
  await nozzle.getByLabel('Code').fill('N1');
  await nozzle.getByLabel('Dispenser').selectOption({ label: 'D1' });
  await nozzle.getByLabel('Fuel type').selectOption({ label: 'Petrol' });
  await nozzle.getByLabel('Tank').selectOption({ index: 1 });
  await nozzle.getByRole('button', { name: 'Save' }).click();
  await expect(nozzle).toBeHidden();

  // The shift
  await page.getByRole('link', { name: 'Shifts', exact: true }).click();
  await page.getByRole('button', { name: /Open shift/ }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Open' }).click();
  await page.getByRole('link', { name: /Open Morning shift/ }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Morning shift' })).toBeVisible();

  await page.getByRole('button', { name: 'Assign nozzle' }).click();
  const assign = page.getByRole('dialog');
  await assign.getByLabel('Employee').selectOption({ index: 1 });
  await assign.getByLabel('Nozzle').selectOption({ label: 'N1' });
  await assign.getByLabel('Opening meter').fill('1000');
  await assign.getByRole('button', { name: 'Assign' }).click();
  await expect(page.getByRole('row', { name: /Ravi Kumar/ })).toContainText('Active');

  // A shift with an active assignment cannot be closed: the message is shown, nothing changes.
  await page.getByRole('button', { name: 'Close shift' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Close shift' }).click();
  await expect(page.getByRole('dialog').getByRole('alert')).toBeVisible();
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel' }).click();

  await page.getByRole('button', { name: /Complete/ }).click();
  const complete = page.getByRole('dialog');
  await complete.getByLabel('Closing meter reading').fill('1100.5');
  await complete.getByRole('button', { name: 'Complete assignment' }).click();
  await expect(complete).toBeHidden();
  await expect(page.getByRole('row', { name: /Ravi Kumar/ })).toContainText('1,100.500');

  await page.getByRole('button', { name: 'Close shift' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Close shift' }).click();
  await expect(page.getByText('Closed', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Reopen shift' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Reopen shift' }).click();
  await expect(page.getByText('Open', { exact: true })).toBeVisible();
});

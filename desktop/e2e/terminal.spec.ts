import { expect, setupPump, showTankNumbers, signIn, test } from './fixtures';

test('a quick ₹1,000 credit sale to a new customer at a priced pump: exact preview, receipt card, stock falls', async ({
  launched,
}) => {
  const { page } = launched;
  await signIn(page, 'manager1');
  await expect(page.getByRole('heading', { level: 1, name: /Tanks/ })).toBeVisible();
  await setupPump(page, '102.50');

  await page.getByRole('link', { name: 'Terminal' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Terminal' })).toBeVisible();
  // the office desk offers only the sales that are typed one by one
  await expect(page.getByRole('button', { name: 'Cash', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'DTP Card' })).toBeVisible();
  // 500 / 102.50 = 4.878... -> shown to two places
  await expect(page.getByText(/Volume: 4.88 L/)).toBeVisible();
  await page.getByRole('button', { name: '₹1000' }).click();
  await expect(page.getByText(/Volume: 9.76 L\s+Total: ₹1,000.00/)).toBeVisible();
  // a customer who is not in the list yet is made on the spot; the vehicle number is required
  await page.getByLabel(/^Customer/).selectOption({ label: '+ New customer' });
  await page.getByLabel('New customer name').fill('Sample Roadways');
  await page.getByRole('button', { name: 'Complete sale' }).click();
  await expect(page.getByRole('alert')).toContainText('Enter the vehicle number');
  await page.getByLabel('Vehicle number').fill('mh 12 ab 1234');
  await page.getByRole('button', { name: 'Complete sale' }).click();

  await expect(page.getByRole('heading', { name: 'Sale recorded' })).toBeVisible();
  await expect(page.getByText('Amount: ₹1,000.00')).toBeVisible();
  await expect(page.getByText('Vehicle: MH12AB1234')).toBeVisible(); // saved in capitals with no spaces
  await page.getByRole('button', { name: 'New sale' }).click();
  await expect(page.getByText(/Recent sales on this nozzle/)).toBeVisible();

  await page.getByRole('link', { name: 'Tanks' }).click();
  await showTankNumbers(page);
  // 1000 / 102.50 = 9.7560975... litres issued, stored to a millilitre: 2500.500 - 9.756
  await expect(
    page.getByRole('listitem').filter({ has: page.getByRole('heading', { name: 'T1' }) }),
  ).toContainText('2,490.744');
});

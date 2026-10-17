import { expect, setupPump, signIn, test } from './fixtures';

// Credit is what goes wrong most: a bill that passes the customer's limit must stop and ask an owner,
// and what the owner allowed must show in the customer's history.
test('a credit bill past the limit asks for an owner, who allows it with their own password; it is recorded', async ({
  launched,
}) => {
  const { page } = launched;
  const { api } = await setupPump(page);
  const customer = (await api('POST', '/customers', { name: 'Limit Test Traders' })) as {
    id: string;
  };
  await api('POST', '/credit/accounts', {
    customer_id: customer.id,
    credit_limit: '500.00',
    payment_due_days: 30,
  });

  await page.evaluate(() => (location.hash = '#/terminal'));
  await signIn(page, 'manager1', undefined, { home: true });
  await expect(page.getByRole('heading', { level: 1, name: 'Terminal' })).toBeVisible();
  await page.getByRole('button', { name: 'Credit', exact: true }).click();
  await page.getByLabel(/Customer/).selectOption({ label: 'Limit Test Traders' });
  await page.getByLabel('Amount (₹)').fill('600');
  await page.getByLabel('Vehicle number').fill('MH 12 AB 1234');

  // the limit is shown while the bill is typed
  const panel = page.getByRole('region', { name: 'Credit limit' });
  await expect(panel).toContainText('₹600.00');
  await expect(panel).toContainText('an owner has to allow this bill');

  await page.getByRole('button', { name: 'Complete sale' }).click();
  const dialog = page.getByRole('dialog', { name: 'An owner must allow this bill' });
  await expect(dialog).toContainText('over the credit limit');
  await dialog.getByLabel('Owner', { exact: true }).selectOption({ label: 'Owner1 Tester' });
  await dialog.getByLabel("Owner's password").fill('not-the-password');
  await dialog.getByRole('button', { name: 'Allow this bill' }).click();
  await expect(dialog.getByRole('alert')).toContainText(/not correct/);

  await dialog.getByLabel("Owner's password").fill('Passw0rd!x');
  await dialog.getByLabel(/Why is this being allowed/).fill('regular client, pays on Friday');
  await dialog.getByRole('button', { name: 'Allow this bill' }).click();
  await expect(page.getByRole('heading', { name: 'Sale recorded' })).toBeVisible();

  await page.evaluate((id) => (location.hash = `#/credit/customers/${id}`), customer.id);
  await expect(page.getByRole('heading', { name: 'Limit Test Traders' })).toBeVisible();
  await expect(page.getByText(/allowed by owner1/)).toBeVisible();
  await expect(page.getByText(/regular client, pays on Friday/)).toBeVisible();
  await expect(page.getByRole('list', { name: 'Summary' })).toContainText('₹600.00');
});

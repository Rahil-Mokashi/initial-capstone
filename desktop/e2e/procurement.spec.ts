import { expect, showTankNumbers, signIn, test } from './fixtures';

test('supplier, purchase order, tanker unloaded into the tank, invoice, payment', async ({
  launched,
}) => {
  const { page } = launched;
  await signIn(page, 'manager1');

  // Supplier
  await page.getByRole('link', { name: 'Suppliers' }).click();
  await page.getByRole('button', { name: /Add supplier/ }).click();
  await page.getByRole('dialog').getByLabel('Name').fill('Indian Oil');
  await page.getByRole('dialog').getByRole('button', { name: 'Save' }).click();
  await expect(page.getByRole('cell', { name: 'Indian Oil', exact: true })).toBeVisible();

  // Purchase order for Petrol
  await page.getByRole('tab', { name: 'Purchase Orders' }).click();
  await page.getByRole('button', { name: /Create purchase order/ }).click();
  let dialog = page.getByRole('dialog');
  await dialog.getByLabel('Supplier', { exact: true }).selectOption({ label: 'Indian Oil' });
  await dialog.getByLabel('Fuel').selectOption({ label: 'Petrol' });
  await dialog.getByLabel('Quantity (L)').fill('1000');
  await dialog.getByRole('button', { name: /Add item/ }).click();
  await dialog.getByRole('button', { name: 'Create order' }).click();
  await expect(dialog).toBeHidden();
  await page.getByRole('link', { name: 'PO-0001' }).first().click();

  // Tanker arrival
  await page.getByRole('button', { name: /Record delivery arrival/ }).click();
  dialog = page.getByRole('dialog');
  await dialog.getByLabel('Tank', { exact: true }).selectOption({ label: 'T1 (Petrol)' });
  await dialog.getByLabel('Received by').selectOption({ index: 1 });
  await dialog.getByLabel('Tanker number').fill('MH12-1234');
  await dialog.getByRole('button', { name: 'Record arrival' }).click();
  await expect(dialog).toBeHidden();
  await page.getByRole('link', { name: 'MH12-1234' }).click();

  // Workflow, in order
  await page.getByRole('button', { name: 'Verify documents' }).click();
  await expect(page.getByRole('button', { name: 'Verify quality' })).toBeEnabled();
  await page.getByRole('button', { name: 'Verify quality' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Verify quality' }).click();
  await page.getByRole('button', { name: 'Record pre-dip reading' }).click();
  await page.getByRole('dialog').getByLabel('Dip value (L)').fill('2500.5');
  await page.getByRole('dialog').getByRole('button', { name: 'Record pre-dip' }).click();
  await page.getByRole('button', { name: 'Record post-dip and unload' }).click();
  await page.getByRole('dialog').getByLabel('Dip value (L)').fill('3500.5');
  await page.getByRole('dialog').getByRole('button', { name: 'Record post-dip and unload' }).click();
  await expect(page.getByText('1,000.000 L')).toBeVisible();

  // The tank now holds the received fuel
  await page.getByRole('link', { name: 'Tanks' }).click();
  await showTankNumbers(page);
  await expect(
    page.getByRole('listitem').filter({ has: page.getByRole('heading', { name: 'T1' }) }),
  ).toContainText('3,500.500');

  // Invoice and payment
  await page.getByRole('link', { name: 'Procurement', exact: true }).click();
  await page.getByRole('tab', { name: 'Invoices' }).click();
  await page.getByRole('button', { name: /Record invoice/ }).click();
  dialog = page.getByRole('dialog');
  await dialog.getByLabel('Invoice number').fill('INV-1');
  await dialog.getByLabel('Supplier', { exact: true }).selectOption({ label: 'Indian Oil' });
  await dialog.getByLabel('Amount', { exact: true }).fill('1000');
  await dialog.getByRole('button', { name: 'Save' }).click();
  await expect(dialog).toBeHidden();
  await page.getByRole('link', { name: 'INV-1' }).click();
  await page.getByRole('button', { name: 'Record payment' }).click();
  await page.getByRole('dialog').getByLabel('Amount', { exact: true }).fill('1000');
  await page.getByRole('dialog').getByRole('button', { name: 'Save' }).click();
  await expect(page.getByRole('cell', { name: '₹1,000' }).first()).toBeVisible();
  await expect(page.getByText('Paid', { exact: true })).toBeVisible();
});

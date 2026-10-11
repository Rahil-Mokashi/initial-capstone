import { expect, setupPump, signIn, test } from './fixtures';

test('declare a short cash drawer, approve it, book the shortage on an employee and take a repayment', async ({
  launched,
}) => {
  const { page } = launched;
  await signIn(page, 'manager1');
  await expect(page.getByRole('heading', { level: 1, name: /Tanks/ })).toBeVisible();
  const pump = await setupPump(page);
  await pump.api('POST', '/terminal/sales', {
    mode: 'amount',
    value: '1000.00',
    payment_method: 'cash',
    shift_id: pump.shiftId,
    nozzle_id: pump.nozzleId,
    employee_id: pump.employeeId,
  });

  await page.getByRole('link', { name: 'Reconciliation' }).click();
  await page.getByRole('button', { name: /Reconcile shift/ }).click();
  let dialog = page.getByRole('dialog');
  await dialog.getByLabel('Shift').selectOption({ index: 1 });
  await dialog.getByLabel(/Declared Cash \(expected 1000.00\)/).fill('900');
  await dialog.getByRole('button', { name: 'Reconcile' }).click();
  await expect(dialog).toBeHidden();
  const row = page.getByRole('row').filter({ hasText: 'Cash: -100.00' });
  await expect(row).toContainText('Pending Approval');

  await row.getByRole('radio').check();
  await page.getByRole('button', { name: 'Approve selected' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Approve' }).click();
  await expect(row).not.toContainText('Pending Approval');

  await page.getByRole('button', { name: /Record shortage/ }).click();
  dialog = page.getByRole('dialog');
  await dialog.getByLabel('Reconciliation line').selectOption({ index: 1 });
  await dialog.getByLabel('Responsible employee').selectOption({ index: 1 });
  await dialog.getByRole('button', { name: 'Record' }).click();
  await expect(dialog).toBeHidden();
  const shortage = page.getByRole('table', { name: 'Employee cash shortages' }).getByRole('row', { name: /Ravi Kumar/ });
  await expect(shortage).toContainText('₹100.00');
  await expect(shortage).toContainText('Outstanding');

  await page.getByRole('button', { name: /Record cash movements/ }).click();
  dialog = page.getByRole('dialog');
  await dialog.getByLabel('Shift').selectOption({ index: 1 });
  await dialog.getByLabel('Final handed over').fill('900');
  await dialog.getByRole('button', { name: 'Record' }).click();
  await expect(dialog).toBeHidden();

  await page.getByRole('button', { name: /Record recovery/ }).click();
  dialog = page.getByRole('dialog');
  await dialog.getByLabel('Shortage').selectOption({ index: 1 });
  await dialog.getByLabel('Repaid into shift').selectOption({ index: 1 });
  await dialog.getByLabel('Amount recovered').fill('');
  await dialog.getByLabel('Amount recovered').pressSequentially('100');
  await dialog.getByRole('button', { name: 'Record' }).click();
  await expect(dialog).toBeHidden();
  await expect(shortage).toContainText('Recovered');
});

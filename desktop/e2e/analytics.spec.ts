import { expect, setupPump, signIn, test } from './fixtures';

test('business insights: revenue for the period and a forecast per fuel', async ({ launched }) => {
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

  await page.getByRole('link', { name: 'Reports' }).click();
  await page.getByRole('link', { name: /Business Insights/ }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Business Insights' })).toBeVisible();
  const table = page.getByRole('table', { name: /Business Performance - Day/ });
  await expect(table.getByRole('row', { name: /Total Revenue/ })).toContainText('1000.00');

  await page.getByLabel('Period').selectOption('month');
  await page.getByRole('button', { name: /Generate/ }).click();
  await expect(page.getByRole('table', { name: /Business Performance - Month/ })).toBeVisible();

  await page.getByRole('tab', { name: 'Sales Forecast' }).click();
  await expect(page.getByRole('table', { name: 'Sales Forecast' })).toContainText('Petrol');
});

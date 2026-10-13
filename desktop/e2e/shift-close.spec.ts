import { expect, setupPump, signIn, test } from './fixtures';

// How a shift really ends: the data-entry person types the closing master reading, nothing per sale.
test('the data-entry person closes a nozzle by typing its closing reading', async ({
  launched,
}) => {
  const { page } = launched;
  const { api, shiftId } = await setupPump(page);
  await page.evaluate(() => (location.hash = '#/shift-close'));
  await signIn(page, 'dataentry1', undefined, { home: true });
  await expect(page.getByRole('heading', { level: 1, name: 'Shift Close' })).toBeVisible();
  await page.getByLabel('Closing for N1').fill('40');
  await page.getByRole('button', { name: /Close 1 nozzle/ }).click();
  await expect(page.getByText('1 nozzle(s) closed.')).toBeVisible();
  await expect(page.getByText('Closed', { exact: true })).toBeVisible();
  const sales = (await api('GET', '/sales')) as unknown as {
    items: Array<{ quantity: string; payment_method: string }>;
  };
  expect(sales.items.map((s) => [s.quantity, s.payment_method])).toEqual([['40.000', 'cash']]);
  expect(shiftId).toBeTruthy();
});

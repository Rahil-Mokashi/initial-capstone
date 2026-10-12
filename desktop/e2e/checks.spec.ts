import { expect, setupPump, signIn, test } from './fixtures';

test.describe('checks', () => {
  test('an owner sees a failing check, with both figures, and opens the tank behind it', async ({
    launched,
  }) => {
    const { page } = launched;
    const { api, shiftId } = await setupPump(page);

    // The cashier closes the nozzle: the app settles the rest of the meter as one cash sale.
    const assignments = (await api('GET', `/shifts/${shiftId}/assignments`)) as unknown as Array<{
      id: string;
    }>;
    await api('POST', `/shift-assignments/${assignments[0]!.id}/complete`, {
      closing_meter: '40.000',
    });
    // The local business day (the Sweden locale prints YYYY-MM-DD). setupPump dates its shift in UTC, which
    // near midnight is a different day, so the dip check below is dated by the local day on purpose.
    const shiftDay = new Date().toLocaleDateString('sv');
    // The dip says 2,000 L where the book says 2,460.500 L.
    const tanks = (await api('GET', '/tanks')) as unknown as Array<{ id: string; code: string }>;
    const t1 = tanks.find((t) => t.code === 'T1')!;
    await api('POST', `/tanks/${t1.id}/reconciliations`, {
      reconciliation_date: shiftDay,
      physical_stock: '2000.000',
    });

    await page.evaluate(() => (location.hash = '#/checks'));
    await signIn(page, 'owner1', undefined, { home: true });
    await expect(page.getByRole('heading', { level: 1, name: 'Checks' })).toBeVisible();
    await page.getByLabel('Day').fill(shiftDay);

    const results = page.getByRole('list', { name: 'Check results' });
    const first = results
      .getByRole('listitem')
      .filter({ hasText: 'T1: dip reading matches the book stock' })
      .first();
    await expect(first).toContainText('T1: dip reading matches the book stock');
    await expect(first).toContainText('Failed');
    await expect(first).toContainText('2,460.500 L');
    await expect(first).toContainText('2,000.000 L');
    await expect(page.getByText(/\d+ of \d+ checks passed, \d+ failed/)).toBeVisible();
    // failures are listed first: the first row on the page is a failure
    await expect(results.getByRole('listitem').first()).toContainText('Failed');

    await first.getByRole('link', { name: /Open T1/ }).click();
    await expect(page.getByRole('heading', { name: 'Tank T1' })).toBeVisible();
  });

  test('the cashier lands on the shift entry list and has no Checks screen', async ({
    launched,
  }) => {
    const { page } = launched;
    await signIn(page, 'dataentry1', undefined, { home: true });
    await expect(page.getByRole('region', { name: /Shift entry/ })).toBeVisible();
    const nav = page.getByRole('navigation', { name: 'Main' });
    await expect(nav.getByRole('link', { name: 'Checks' })).toHaveCount(0);
    await expect(nav.getByRole('link', { name: 'Employees' })).toHaveCount(0);
    await expect(nav.getByRole('link', { name: 'Expenses' })).toBeVisible();
  });
});

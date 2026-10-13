import { mkdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { expect, setupPump, signIn, test } from './fixtures';
import { repoRoot } from './global-setup';

// The one-screen close: readings + money collected + tally with the shortage beside them.
test('the cashier closes a shift on one screen and sees the shortage as they type', async ({ launched }) => {
  const { page } = launched;
  await setupPump(page); // Petrol at 100.00, nozzle N1 opening 0 on tank T1, an open shift
  await page.evaluate(() => (location.hash = '#/close-shift'));
  await signIn(page, 'dataentry1', undefined, { home: true });
  await expect(page.getByRole('heading', { level: 1, name: 'Close Shift' })).toBeVisible();
  await expect(page.getByLabel('Testing for N1')).toHaveValue('5'); // the usual testing is already filled in
  await page.getByLabel('Closing for N1').fill('505'); // 505 on the meter, 5 of it testing: 500 L sold = 50,000.00
  await page.getByLabel('CARD', { exact: true }).fill('10000');
  await page.getByLabel('PHONE PAY').fill('5000');
  await page.getByLabel('Advance', { exact: true }).fill('20000');
  await page.getByLabel('Final', { exact: true }).fill('14000');
  const tally = page.getByRole('complementary', { name: 'Tally' });
  await expect(tally.getByText('Short ₹1,000.00')).toBeVisible();
  await expect(tally.getByText('₹50,000.00').first()).toBeVisible();
  if (process.env.SCREENSHOTS === '1') {
    const out = resolve(repoRoot, 'docs', 'screenshots', 'lan');
    mkdirSync(out, { recursive: true });
    await page.screenshot({ path: join(out, 'close-shift-short.png') });
  }
  // fix the card figure: it balances
  await page.getByLabel('CARD', { exact: true }).fill('11000');
  await expect(tally.getByText('Balanced')).toBeVisible();
  await page.getByRole('button', { name: /Close shift/ }).click();
  await expect(page.getByText('Shift closed and saved.')).toBeVisible();
  await expect(tally.getByText('Balanced')).toBeVisible();
  await expect(page.getByLabel('Advance (recorded earlier)')).toBeDisabled();
});

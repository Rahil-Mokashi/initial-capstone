import { apiAs, expect, setupPump, signIn, test } from './fixtures';

// The owners' biggest pain: checking a bank credit against the books by hand. An accountant imports the
// statement, the app matches what it can, and the day table shows expected against received.
test('an accountant imports a statement and the day shows the card settlement matched', async ({
  launched,
}) => {
  const { page } = launched;
  const { api, shiftId } = await setupPump(page);
  const shiftDay = ((await api('GET', `/shifts/${shiftId}`)) as { shift_date: string }).shift_date;
  const rows = (await api('GET', `/shift-totals/${shiftId}`)) as unknown as Array<{
    tender_id: string;
    name: string;
  }>;
  await api(
    'PUT',
    `/shift-totals/${shiftId}/${rows.find((r) => r.name === 'DTP Card')!.tender_id}`,
    {
      amount: '10000.00',
    },
  );
  const accountant = await apiAs(page, 'accountant1');
  await accountant('POST', '/bank/accounts', {
    name: 'Wallet Bank',
    account_mask: 'XXXX1111',
    modes: ['DTP Card'],
  });

  const [y, m, d] = shiftDay.split('-');
  const csv =
    'Date,Narration,Withdrawal,Deposit,Balance\n' +
    `${d}/${m}/${y},DTP FLEET CARD SETTLEMENT,,10000.00,110000.00\n`;

  await page.evaluate(() => (location.hash = '#/bank'));
  await signIn(page, 'accountant1', undefined, { home: true });
  await expect(page.getByRole('heading', { level: 1, name: 'Bank Matching' })).toBeVisible();
  await page.getByLabel('From').fill(shiftDay);
  await page.getByLabel('To').fill(shiftDay);

  await page.getByRole('tab', { name: 'Import a statement' }).click();
  await page
    .getByLabel('Statement file')
    .setInputFiles({ name: 'stmt.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) });
  await page.getByRole('button', { name: 'Preview (stores nothing)' }).click();
  const preview = page.getByLabel('Import preview');
  await expect(preview).toContainText('1 line(s) read');
  await preview.getByRole('button', { name: /Import 1 new line/ }).click();
  await expect(page.getByText('1 new line(s) imported.')).toBeVisible();

  await page.getByRole('button', { name: 'Check the books against the bank' }).click();
  await page.getByRole('tab', { name: 'Day by day' }).click();
  const table = page.getByRole('table', { name: 'Expected against received, by day' });
  const dtp = table.getByRole('row', { name: /DTP Card/ });
  await expect(dtp).toContainText('₹10,000.00');
  await expect(dtp).toContainText('Matched');
});

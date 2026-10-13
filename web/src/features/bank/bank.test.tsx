import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { json } from '@/test/mockApi';
import { guessMapping } from './ImportTab';

beforeEach(() => session.set(null));
afterEach(() => {
  vi.unstubAllGlobals();
  delete window.pperp;
});

const MANAGE = ['bank_recon.view', 'bank_recon.manage'];
const day = (over: Record<string, unknown> = {}) => ({
  day: '2026-10-12',
  mode: 'Paytm',
  label: 'PTM',
  expected: '414760.00',
  received: '414760.00',
  charges: '0.00',
  suggested: '0.00',
  unmatched: '0.00',
  status: 'matched',
  ...over,
});
const row = (over: Record<string, unknown> = {}) => ({
  id: 'r1',
  bank_account_id: 'a1',
  txn_date: '2026-10-12',
  description: 'TRUST DONATION RECEIVED',
  reference: null,
  debit: '0.00',
  credit: '777.00',
  balance: '100777.00',
  match_id: null,
  match_status: null,
  match_kind: null,
  locked: false,
  ...over,
});
const expectedRow = (over: Record<string, unknown> = {}) => ({
  id: 'e1',
  mode: 'cash_deposit',
  label: 'Cash deposits',
  business_date: '2026-10-12',
  win_to: '2026-10-16',
  amount: '60000.00',
  reference: null,
  description: 'Cash deposit to Bank of India (12-10-2026 Evening)',
  match_id: null,
  match_status: null,
  locked: false,
  ...over,
});

const base = (extra: Record<string, unknown> = {}) => ({
  'GET /api/bank/days': () =>
    json(200, [
      day(),
      day({
        mode: 'PhonePe',
        label: 'PHONE PAY',
        expected: '6000.00',
        received: '5950.00',
        charges: '50.00',
      }),
      day({
        mode: 'cash_deposit',
        label: 'Cash deposits',
        expected: '130000.00',
        received: '70000.00',
        unmatched: '60000.00',
        status: 'awaiting',
      }),
    ]),
  'GET /api/bank/suggestions': () =>
    json(200, [
      {
        match_id: 'm1',
        rule: 'many_to_one',
        note: '2 payments added up to this one bank credit',
        charges: '50.00',
        expected: [
          expectedRow({
            id: 'e5',
            mode: 'PhonePe',
            description: 'PHONE PAY for 12-10-2026 Morning',
            amount: '5000.00',
          }),
          expectedRow({
            id: 'e6',
            mode: 'PhonePe',
            description: 'PHONE PAY for 12-10-2026 Evening',
            amount: '1000.00',
          }),
        ],
        rows: [row({ id: 'r9', description: 'PHONEPE SETTLEMENT', credit: '5950.00' })],
      },
    ]),
  'GET /api/bank/exceptions': () =>
    json(200, {
      unmatched_credits: [row()],
      aged_expected: [{ expected: expectedRow(), age_days: 2 }],
      total_charges: '50.00',
      suggestions: 1,
      broken_imports: [],
    }),
  'GET /api/bank/rows': () =>
    json(200, [
      row({
        id: 'r2',
        description: 'DTP FLEET CARD',
        credit: '10000.00',
        match_id: 'm2',
        match_status: 'confirmed',
        match_kind: 'match',
      }),
    ]),
  'GET /api/bank/accounts': () =>
    json(200, [{ id: 'a1', name: 'Bank of India', account_mask: 'XXXX1234', modes: ['Paytm'] }]),
  'GET /api/bank/modes': () =>
    json(200, [
      { mode: 'Paytm', label: 'PTM' },
      { mode: 'cash_deposit', label: 'Cash deposits' },
    ]),
  ...extra,
});

describe('Bank Matching', () => {
  it('shows each mode expected against received with Indian grouping and says in words where it stands', async () => {
    await openAs(MANAGE, '/bank', 'Bank Matching', base());
    const table = await screen.findByRole('table', { name: 'Expected against received, by day' });
    const ptm = within(table).getByRole('row', { name: /PTM/ });
    expect(within(ptm).getAllByText('₹4,14,760.00')).toHaveLength(2); // expected and received
    expect(within(ptm).getByText('Matched')).toBeInTheDocument();
    const phone = within(table).getByRole('row', { name: /PHONE PAY/ });
    expect(within(phone).getByText('₹50.00')).toBeInTheDocument(); // the bank's charge
    const cash = within(table).getByRole('row', { name: /Cash deposits/ });
    expect(within(cash).getByText('On its way')).toBeInTheDocument();
    expect(within(cash).getByText('₹60,000.00')).toBeInTheDocument();
  });

  it('confirms a suggested batch settlement and shows the charge that would be recorded', async () => {
    const api = await openAs(
      MANAGE,
      '/bank',
      'Bank Matching',
      base({
        'POST /api/bank/matches/m1/confirm': () =>
          json(200, { id: 'm1', status: 'confirmed', kind: 'match', locked: false }),
      }),
    );
    expect(
      await screen.findByText('2 payments added up to this one bank credit'),
    ).toBeInTheDocument();
    expect(screen.getByText('Bank charges of ₹50.00 would be recorded')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Confirm this match' }));
    await waitFor(() =>
      expect(api.calls.some((c) => c.key === 'POST /api/bank/matches/m1/confirm')).toBe(true),
    );
  });

  it("lets a person mark a stray credit as not the pump's, with a reason, and never forces a match", async () => {
    const api = await openAs(
      MANAGE,
      '/bank',
      'Bank Matching',
      base({
        'POST /api/bank/rows/r1/not-ours': () =>
          json(201, { id: 'm3', status: 'confirmed', kind: 'not_ours', locked: false }),
      }),
    );
    const list = await screen.findByRole('list', { name: 'Unmatched bank credits' });
    expect(within(list).getByText(/TRUST DONATION RECEIVED/)).toBeInTheDocument();
    await userEvent.click(within(list).getByRole('button', { name: "Not the pump's" }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText(/Reason/), 'goodwill trust');
    await userEvent.click(within(dialog).getByRole('button', { name: "Mark as not the pump's" }));
    await waitFor(() =>
      expect(api.calls.some((c) => c.key === 'POST /api/bank/rows/r1/not-ours')).toBe(true),
    );
    expect(api.calls.find((c) => c.key === 'POST /api/bank/rows/r1/not-ours')!.body).toEqual({
      reason: 'goodwill trust',
    });
    expect(screen.getByRole('list', { name: 'Expected but not received' })).toHaveTextContent(
      'Cash deposit to Bank of India',
    );
  });

  it('a view-only person can look but not change anything', async () => {
    await openAs(['bank_recon.view'], '/bank', 'Bank Matching', base());
    await screen.findByRole('table', { name: 'Expected against received, by day' });
    expect(
      screen.queryByRole('button', { name: 'Check the books against the bank' }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Match by hand' })).not.toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'Import a statement' })).not.toBeInTheDocument();
  });

  it('only an owner sees Lock, and a locked match cannot be undone from the list', async () => {
    await openAs([...MANAGE, 'bank_recon.lock'], '/bank', 'Bank Matching', base());
    await userEvent.click(await screen.findByRole('tab', { name: 'Statement lines' }));
    const table = await screen.findByRole('table', { name: 'Bank statement lines' });
    expect(within(table).getByText('Matched')).toBeInTheDocument();
    expect(within(table).getByRole('button', { name: 'Lock' })).toBeInTheDocument();
    expect(within(table).getByRole('button', { name: 'Undo match' })).toBeInTheDocument();
  });
});

describe('Import a statement', () => {
  it('guesses the columns from the words banks use', () => {
    const m = guessMapping(
      [
        'Txn Date',
        'Narration',
        'Withdrawal Amt.',
        'Deposit Amt.',
        'Closing Balance',
        'Chq./Ref.No.',
      ],
      2,
    );
    expect(m).toMatchObject({
      date_col: 'Txn Date',
      description_col: 'Narration',
      debit_col: 'Withdrawal Amt.',
      credit_col: 'Deposit Amt.',
      balance_col: 'Closing Balance',
      reference_col: 'Chq./Ref.No.',
      header_row: 2,
    });
  });

  it('reads the headers, previews without storing, warns about missing rows, then imports', async () => {
    const file = new File(
      ['Txn Date,Narration,Withdrawal,Deposit,Balance\n01/10/2026,A,,100,100\n'],
      'stmt.csv',
      { type: 'text/csv' },
    );
    const api = await openAs(
      MANAGE,
      '/bank',
      'Bank Matching',
      base({
        'POST /api/bank/accounts/a1/headers': () =>
          json(200, {
            headers: ['Txn Date', 'Narration', 'Withdrawal', 'Deposit', 'Balance'],
            first_rows: [],
          }),
        'GET /api/bank/accounts/a1/profiles': () => json(200, []),
        'POST /api/bank/accounts/a1/preview': () =>
          json(200, {
            headers: [],
            sample: [
              {
                id: '2',
                bank_account_id: 'a1',
                txn_date: '2026-10-01',
                description: 'A',
                reference: null,
                debit: '0.00',
                credit: '100.00',
                balance: '100.00',
              },
            ],
            row_count: 5,
            problems: [],
            new_rows: 4,
            duplicate_rows: 1,
            opening_balance: '0.00',
            closing_balance: '100.00',
            breaks: [{ line: 4, gap: '20000.00' }],
            date_from: '2026-10-01',
            date_to: '2026-10-03',
            same_file_before: false,
          }),
        'POST /api/bank/accounts/a1/import': () =>
          json(201, {
            id: 'i1',
            filename: 'stmt.csv',
            row_count: 5,
            new_rows: 4,
            duplicate_rows: 1,
            continuity_ok: false,
            break_count: 1,
            imported_at: '2026-10-13T00:00:00Z',
          }),
      }),
    );
    await userEvent.click(await screen.findByRole('tab', { name: 'Import a statement' }));
    await userEvent.upload(await screen.findByLabelText('Statement file'), file);
    await userEvent.click(await screen.findByRole('button', { name: 'Preview (stores nothing)' }));
    const preview = await screen.findByLabelText('Import preview');
    expect(within(preview).getByText(/new,/)).toBeInTheDocument();
    expect(within(preview).getByRole('alert')).toHaveTextContent('Rows are missing');
    expect(within(preview).getByRole('alert')).toHaveTextContent('₹20,000.00');
    expect(api.calls.some((c) => c.key === 'POST /api/bank/accounts/a1/import')).toBe(false); // preview stored nothing
    await userEvent.click(within(preview).getByRole('button', { name: /Import 4 new line/ }));
    await waitFor(() =>
      expect(api.calls.some((c) => c.key === 'POST /api/bank/accounts/a1/import')).toBe(true),
    );
    const sent = api.calls.find((c) => c.key === 'POST /api/bank/accounts/a1/import')!.body as {
      filename: string;
      mapping: Record<string, unknown>;
    };
    expect(sent.filename).toBe('stmt.csv');
    expect(sent.mapping).toMatchObject({
      date_col: 'Txn Date',
      credit_col: 'Deposit',
      debit_col: 'Withdrawal',
    });
  });
});

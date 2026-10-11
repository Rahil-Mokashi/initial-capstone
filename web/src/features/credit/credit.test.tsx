import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { apiError, json } from '@/test/mockApi';

const MANAGE = ['credit.view', 'credit.manage', 'sale.view', 'sale.manage'];
const acct = (over: Record<string, unknown> = {}) => ({
  customer_id: 'c1',
  customer: 'ACME',
  credit_limit: '10000.00',
  outstanding: '1500.00',
  overdue: false,
  payment_due_days: 30,
  ...over,
});
const base = (
  rows = [
    acct(),
    acct({ customer_id: 'c2', customer: 'Beta', overdue: true, outstanding: '0.00' }),
  ],
) => ({
  'GET /api/credit/accounts': () => json(200, rows),
  'GET /api/customers': () =>
    json(200, [
      { id: 'c1', name: 'ACME', phone: null, email: null, address: null, status: 'active' },
      { id: 'c3', name: 'Gamma', phone: null, email: null, address: null, status: 'active' },
    ]),
});

beforeEach(() => session.set(null));
afterEach(() => {
  vi.unstubAllGlobals();
  delete window.pperp;
});

describe('credit accounts', () => {
  it('shows limit, outstanding and overdue; actions that need an account stay disabled until one is selected', async () => {
    await openAs(MANAGE, '/credit', 'Credit Management', base());
    expect(await screen.findByRole('cell', { name: '₹1,500.00' })).toBeInTheDocument();
    expect(screen.getByText('Yes')).toBeInTheDocument(); // overdue badge
    expect(screen.getByRole('button', { name: 'View statement' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Change limit' })).toBeDisabled();
    await userEvent.click(screen.getByRole('radio', { name: 'Select ACME' }));
    expect(screen.getByRole('button', { name: 'View statement' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Change limit' })).toBeEnabled();
  });

  it('opens an account with the Qt defaults (10000 limit, 30 days)', async () => {
    const api = await openAs(MANAGE, '/credit', 'Credit Management', {
      ...base(),
      'POST /api/credit/accounts': () => json(201, acct({ customer_id: 'c3', customer: 'Gamma' })),
    });
    await userEvent.click(await screen.findByRole('button', { name: /Open credit account/ }));
    const d = screen.getByRole('dialog');
    await userEvent.click(within(d).getByRole('button', { name: 'Open account' }));
    expect(
      await within(d).findByText('Choose a customer, or add a new one, first.'),
    ).toBeInTheDocument();
    await userEvent.selectOptions(await within(d).findByLabelText('Customer'), 'c3');
    expect(within(d).getByLabelText('Credit limit')).toHaveValue('10000');
    await userEvent.click(within(d).getByRole('button', { name: 'Open account' }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/credit/accounts')?.body).toEqual({
        customer_id: 'c3',
        credit_limit: '10000',
        payment_due_days: 30,
      }),
    );
  });

  it('adds a new customer from inside the open-account flow and comes back with them selected', async () => {
    const api = await openAs(MANAGE, '/credit', 'Credit Management', {
      ...base(),
      'POST /api/customers': () =>
        json(201, {
          id: 'c9',
          name: 'Newco',
          phone: null,
          email: null,
          address: null,
          status: 'active',
        }),
    });
    await userEvent.click(await screen.findByRole('button', { name: /Open credit account/ }));
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: /Add new customer/ }),
    );
    // only one dialog at a time
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
    const d = screen.getByRole('dialog');
    await userEvent.type(within(d).getByLabelText('Name'), 'Newco');
    await userEvent.click(within(d).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(api.calls.some((c) => c.key === 'POST /api/customers')).toBe(true));
    expect(await screen.findByRole('heading', { name: 'Open credit account' })).toBeInTheDocument();
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
  });

  it('records a payment: customer pre-filled from the selected row, credit is not a payment method', async () => {
    const api = await openAs(MANAGE, '/credit', 'Credit Management', {
      ...base(),
      'POST /api/credit/payments': () => json(201, { id: 'p1', amount: '500.00' }),
    });
    await userEvent.click(await screen.findByRole('radio', { name: 'Select Beta' }));
    await userEvent.click(screen.getByRole('button', { name: 'Record payment' }));
    const d = screen.getByRole('dialog');
    expect(within(d).getByLabelText('Customer')).toHaveValue('c2');
    expect(within(d).queryByRole('option', { name: 'Credit' })).not.toBeInTheDocument();
    const amount = within(d).getByLabelText('Amount');
    await userEvent.clear(amount);
    await userEvent.type(amount, '500.255');
    expect(amount).toHaveValue('500.25');
    await userEvent.click(within(d).getByRole('button', { name: 'Record payment' }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/credit/payments')?.body).toEqual({
        customer_id: 'c2',
        amount: '500.25',
        payment_method: 'cash',
      }),
    );
  });

  it('changes the limit with an optional reason and shows a server refusal inside the dialog', async () => {
    let n = 0;
    const api = await openAs(MANAGE, '/credit', 'Credit Management', {
      ...base(),
      'POST /api/credit/accounts/c1/limit': () =>
        n++ === 0
          ? apiError(409, 'conflict', 'New limit is below the outstanding balance')
          : json(200, acct({ credit_limit: '5000.00' })),
    });
    await userEvent.click(await screen.findByRole('radio', { name: 'Select ACME' }));
    await userEvent.click(screen.getByRole('button', { name: 'Change limit' }));
    const d = screen.getByRole('dialog');
    expect(within(d).getByLabelText('New limit')).toHaveValue('10000.00');
    await userEvent.clear(within(d).getByLabelText('New limit'));
    await userEvent.type(within(d).getByLabelText('New limit'), '1000');
    await userEvent.click(within(d).getByRole('button', { name: 'Change limit' }));
    expect(await within(d).findByRole('alert')).toHaveTextContent('below the outstanding');
    await userEvent.clear(within(d).getByLabelText('New limit'));
    await userEvent.type(within(d).getByLabelText('New limit'), '5000');
    await userEvent.click(within(d).getByRole('button', { name: 'Change limit' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(
      api.calls.filter((c) => c.key === 'POST /api/credit/accounts/c1/limit').pop()?.body,
    ).toEqual({
      new_limit: '5000',
      reason: '',
    });
  });

  it('shows the statement with debit/credit columns and hands the report to the print preview', async () => {
    const preview = vi.fn(async () => ({ ok: true }));
    window.pperp = {
      apiBase: '',
      launchSecret: 's',
      files: { pickPath: async () => null, save: async () => ({ ok: true }) },
      print: { preview },
    } as never;
    await openAs(MANAGE, '/credit', 'Credit Management', {
      ...base(),
      'GET /api/credit/accounts/c1/statement': () =>
        json(200, {
          customer: 'ACME',
          entries: [
            {
              entry_date: '2026-10-10',
              description: 'Credit sale R-1',
              debit: '1500.00',
              credit: null,
              running_balance: '1500.00',
            },
            {
              entry_date: '2026-10-11',
              description: 'Payment',
              debit: null,
              credit: '500.00',
              running_balance: '1000.00',
            },
          ],
          running_balance: '1000.00',
          report: {
            title: 'Customer Statement - ACME',
            headers: [],
            rows: [],
            html: '<table>statement</table>',
          },
        }),
    });
    await userEvent.click(await screen.findByRole('radio', { name: 'Select ACME' }));
    await userEvent.click(screen.getByRole('button', { name: 'View statement' }));
    const d = await screen.findByRole('dialog');
    expect(await within(d).findByText('Credit sale R-1')).toBeInTheDocument();
    expect(within(d).getByText('Running balance: ₹1,000.00')).toBeInTheDocument();
    await userEvent.click(within(d).getByRole('button', { name: 'Print preview' }));
    await waitFor(() =>
      expect(preview).toHaveBeenCalledWith('<table>statement</table>', undefined),
    );
    expect(within(d).getByRole('button', { name: 'Export Excel' })).toBeInTheDocument();
    expect(within(d).getByRole('button', { name: 'Export PDF' })).toBeInTheDocument();
  });

  it('view-only users can read accounts and statements but not change anything', async () => {
    await openAs(['credit.view'], '/credit', 'Credit Management', base());
    await screen.findByRole('cell', { name: '₹1,500.00' });
    expect(screen.queryByRole('button', { name: /Open credit account/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Record payment' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'View statement' })).toBeInTheDocument();
  });
});

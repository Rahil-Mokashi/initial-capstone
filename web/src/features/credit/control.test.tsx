import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { apiError, json } from '@/test/mockApi';

beforeEach(() => session.set(null));
afterEach(() => {
  vi.unstubAllGlobals();
  delete window.pperp;
});

const bill = (over: Record<string, unknown> = {}) => ({
  kind: 'sale',
  ref: 'R-1',
  bill_date: '2026-09-01',
  amount: '1000.00',
  paid: '400.00',
  outstanding: '600.00',
  age_days: 41,
  days_to_pay: null,
  vehicle_no: null,
  slip_no: null,
  sale_id: 's1',
  ...over,
});

const detail = (over: Record<string, unknown> = {}) => ({
  customer_id: 'c1',
  name: 'ACME Traders',
  phone: null,
  credit_limit: '5000.00',
  payment_due_days: 30,
  balance: '10100.00',
  available: '-5100.00',
  total_billed: '12000.00',
  total_paid: '1900.00',
  unapplied: '0.00',
  largest_outstanding_ever: '12000.00',
  average_days_to_pay: '12.5',
  overdue: true,
  overdue_days: 11,
  buckets: { '0-30': '9500.00', '31-60': '600.00', '61-90': '0.00', '90+': '0.00' },
  oldest_unpaid: bill(),
  approval: 'pending',
  approved_by: null,
  approved_at: null,
  bills: [
    bill(),
    bill({
      kind: 'bowser',
      ref: 'B1',
      amount: '9500.00',
      paid: '0.00',
      outstanding: '9500.00',
      age_days: 5,
      vehicle_no: 'MH14XX0001',
      slip_no: 'S-7',
      sale_id: null,
    }),
  ],
  payments: [{ pay_date: '2026-09-10', amount: '1900.00', method: 'cash', reference: null }],
  follow_ups: [
    {
      id: 'f1',
      customer_id: 'c1',
      followed_on: '2026-10-10',
      by: 'accountant1',
      method: 'call',
      note: 'says Friday',
      promised_date: '2026-10-14',
      promised_amount: '5000.00',
      status: 'open',
    },
  ],
  overrides: [],
  ...over,
});

describe('customer page', () => {
  it('shows balance, limit, ageing, average days to pay, the oldest unpaid bill, and bowser bills with vehicle and slip', async () => {
    await openAs(['credit.view'], '/credit/customers/c1', 'ACME Traders', {
      'GET /api/credit/customers/c1': () => json(200, detail()),
    });
    const tiles = within(await screen.findByRole('list', { name: 'Summary' }));
    expect(tiles.getByText('₹10,100.00')).toBeInTheDocument();
    expect(tiles.getByText('₹5,000.00')).toBeInTheDocument();
    expect(tiles.getByText('12.5')).toBeInTheDocument();
    expect(tiles.getByText('R-1: 41 days')).toBeInTheDocument();
    expect(screen.getByText('Overdue by 11 day(s)')).toBeInTheDocument();
    expect(screen.getByText('Waiting for an owner to approve credit')).toBeInTheDocument();
    const bills = screen.getByRole('table', { name: 'Bills' });
    expect(within(bills).getByText('Bouser B1')).toBeInTheDocument();
    expect(within(bills).getByText('MH14XX0001 / S-7')).toBeInTheDocument();
    expect(screen.getByText(/Promised ₹5,000.00 by/)).toBeInTheDocument();
    // no approve button without the permission
    expect(screen.queryByRole('button', { name: /Approve credit/ })).not.toBeInTheDocument();
  });

  it('lets an owner approve, and logs a follow-up with a promise for a person who may do recovery', async () => {
    const api = await openAs(
      ['credit.view', 'credit.approve', 'credit.recovery'],
      '/credit/customers/c1',
      'ACME Traders',
      {
        'GET /api/credit/customers/c1': () => json(200, detail()),
        'POST /api/credit/approvals/c1': () => json(200, { id: 'a1' }),
        'POST /api/credit/customers/c1/follow-ups': () => json(201, {}),
      },
    );
    await userEvent.click(
      await screen.findByRole('button', { name: /Approve credit for this customer/ }),
    );
    await waitFor(() =>
      expect(api.calls.some((c) => c.key === 'POST /api/credit/approvals/c1')).toBe(true),
    );
    const form = screen.getByRole('form', { name: 'Log a follow-up' });
    await userEvent.type(within(form).getByLabelText(/What was said/), 'will pay half');
    await userEvent.type(within(form).getByLabelText(/Promised amount/), '2500');
    await userEvent.click(within(form).getByRole('button', { name: 'Log follow-up' }));
    await waitFor(() =>
      expect(api.calls.some((c) => c.key === 'POST /api/credit/customers/c1/follow-ups')).toBe(
        true,
      ),
    );
    expect(
      api.calls.find((c) => c.key === 'POST /api/credit/customers/c1/follow-ups')!.body,
    ).toMatchObject({
      method: 'call',
      note: 'will pay half',
      promised_amount: '2500',
    });
  });

  it('offers the statement as preview, PDF and Excel for the chosen dates', async () => {
    const preview = vi.fn(async (html: string) => ({ ok: html.length > 0 }));
    window.pperp = { print: { preview } } as unknown as typeof window.pperp;
    await openAs(['credit.view'], '/credit/customers/c1', 'ACME Traders', {
      'GET /api/credit/customers/c1': () => json(200, detail()),
      'GET /api/credit/customers/c1/statement': () =>
        json(200, { report: { html: '<p>statement</p>', title: 't', headers: [], rows: [] } }),
    });
    expect(await screen.findByRole('button', { name: /Export PDF/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Export Excel/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Print preview/ }));
    await waitFor(() => expect(preview).toHaveBeenCalledWith('<p>statement</p>', undefined));
  });
});

describe('ageing page', () => {
  it('lists customers by age bucket with totals, the oldest unpaid bill, and who is over the limit', async () => {
    await openAs(['credit.view'], '/credit/ageing', 'Credit Ageing', {
      'GET /api/credit/chase': () => json(200, []),
      'GET /api/credit/ageing': () =>
        json(200, {
          as_of: '2026-10-12',
          bucket_names: ['0-30', '31-60', '61-90', '90+'],
          total_balance: '9600.00',
          totals: { '0-30': '4000.00', '31-60': '2000.00', '61-90': '3000.00', '90+': '600.00' },
          rows: [
            {
              customer_id: 'c1',
              name: 'Old Debtor',
              balance: '2600.00',
              buckets: { '0-30': '0.00', '31-60': '2000.00', '61-90': '0.00', '90+': '600.00' },
              oldest_unpaid_ref: 'O1',
              oldest_unpaid_date: '2026-07-04',
              oldest_unpaid_age: 100,
              credit_limit: '2000.00',
              over_limit: true,
              overdue: true,
            },
          ],
        }),
    });
    const table = await screen.findByRole('table', { name: 'Ageing of credit' });
    expect(within(table).getByRole('link', { name: 'Old Debtor' })).toHaveAttribute(
      'href',
      '/credit/customers/c1',
    );
    expect(within(table).getByText(/O1, .* \(100 days\)/)).toBeInTheDocument();
    expect(within(table).getByText('Over limit')).toBeInTheDocument();
    expect(within(table).getByText('Overdue')).toBeInTheDocument();
    expect(within(table).getAllByText('₹9,600.00').length).toBeGreaterThan(0);
    expect(screen.getByText('Nobody needs chasing today.')).toBeInTheDocument();
  });

  it('shows the promises that have come due above the table', async () => {
    await openAs(['credit.view'], '/credit/ageing', 'Credit Ageing', {
      'GET /api/credit/ageing': () =>
        json(200, {
          as_of: '2026-10-12',
          bucket_names: [],
          total_balance: '0.00',
          totals: {},
          rows: [],
        }),
      'GET /api/credit/chase': () =>
        json(200, [
          {
            customer_id: 'c1',
            name: 'Promised Today',
            reason: 'promise',
            detail: 'Promised to pay today',
            promised_date: '2026-10-12',
            promised_amount: '5000.00',
            balance: '9000.00',
            follow_up_id: 'f1',
          },
          {
            customer_id: 'c2',
            name: 'Gone Quiet',
            reason: 'overdue',
            detail: '20 day(s) past the payment terms, never contacted',
            promised_date: null,
            promised_amount: null,
            balance: '3000.00',
            follow_up_id: null,
          },
        ]),
    });
    expect(await screen.findByText('Promise due')).toBeInTheDocument();
    expect(screen.getByText('Overdue')).toBeInTheDocument();
    expect(screen.getByText(/never contacted/)).toBeInTheDocument();
  });
});

describe('terminal credit limit', () => {
  const ctx = {
    can_pick_freely: true,
    shifts: [{ id: 's1', label: '2026-10-12 Morning' }],
    employees: [{ id: 'e1', label: 'EMP-0001 - Ravi Kumar' }],
    nozzles: [{ id: 'n1', code: 'N1', fuel_type: 'Petrol', rate_per_liter: '100.00' }],
    customers: [{ id: 'c1', label: 'ACME' }],
    my_assignment: null,
  };
  const sale = {
    id: 'x1',
    receipt_number: 'R-0001',
    sale_at: '2026-10-12T08:30:00Z',
    fuel_type: 'Petrol',
    nozzle_id: 'n1',
    nozzle: 'N1',
    customer: 'ACME',
    quantity: '5.000',
    rate_per_liter: '100.00',
    amount: '500.00',
    payment_method: 'credit',
    status: 'completed',
    payment_id: 'p1',
    payment_status: 'success',
  };
  const check = {
    customer_id: 'c1',
    customer_name: 'ACME',
    outstanding: '1800.00',
    credit_limit: '2000.00',
    this_bill: '500.00',
    would_become: '2300.00',
    available: '200.00',
    over_limit: true,
    mode: 'warn',
    approval: 'not_required',
    problem: null,
  };

  it('shows what the customer owes against the limit while the bill is typed', async () => {
    await openAs(['sale.view', 'sale.manage', 'credit.view'], '/terminal', 'Terminal', {
      'GET /api/terminal/context': () => json(200, ctx),
      'GET /api/sales': () => json(200, { total: 0, items: [] }),
      'GET /api/credit/check': () => json(200, check),
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Credit' }));
    await userEvent.selectOptions(screen.getByLabelText(/Customer/), 'c1');
    const panel = await screen.findByRole('region', { name: 'Credit limit' });
    expect(within(panel).getByText('₹1,800.00')).toBeInTheDocument();
    expect(within(panel).getByText('₹2,300.00')).toBeInTheDocument();
    expect(within(panel).getByText(/an owner has to allow this bill/)).toBeInTheDocument();
  });

  it('asks for an owner when the bill passes the limit, then sends the override and records the sale', async () => {
    const posts: unknown[] = [];
    await openAs(['sale.view', 'sale.manage', 'credit.view'], '/terminal', 'Terminal', {
      'GET /api/terminal/context': () => json(200, ctx),
      'GET /api/sales': () => json(200, { total: 0, items: [] }),
      'GET /api/credit/check': () => json(200, check),
      'GET /api/credit/approvers': () => json(200, [{ id: 'o1', name: 'Owner One' }]),
      'POST /api/terminal/sales': (body) => {
        posts.push(body);
        return (body as { credit_override?: unknown }).credit_override
          ? json(201, sale)
          : apiError(
              409,
              'credit_limit_exceeded',
              'ACME would owe 2300.00, over the limit of 2000.00. An owner can allow it.',
              { can_override: true },
            );
      },
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Credit' }));
    await userEvent.selectOptions(screen.getByLabelText(/Customer/), 'c1');
    await userEvent.click(screen.getByRole('button', { name: 'Complete sale' }));
    const dialog = await screen.findByRole('dialog', { name: 'An owner must allow this bill' });
    expect(within(dialog).getByText(/over the limit of 2000.00/)).toBeInTheDocument();
    await userEvent.type(within(dialog).getByLabelText("Owner's password"), 'OwnerPass1!');
    await userEvent.type(
      within(dialog).getByLabelText(/Why is this being allowed/),
      'pays on Friday',
    );
    await userEvent.click(within(dialog).getByRole('button', { name: 'Allow this bill' }));
    expect(await screen.findByRole('heading', { name: 'Sale recorded' })).toBeInTheDocument();
    expect(posts).toHaveLength(2);
    expect(posts[1]).toMatchObject({
      credit_override: {
        approver_id: 'o1',
        credential: 'OwnerPass1!',
        use_pin: false,
        reason: 'pays on Friday',
      },
    });
  });

  it('keeps the dialog open and says why when the owner password is wrong', async () => {
    await openAs(['sale.view', 'sale.manage', 'credit.view'], '/terminal', 'Terminal', {
      'GET /api/terminal/context': () => json(200, ctx),
      'GET /api/sales': () => json(200, { total: 0, items: [] }),
      'GET /api/credit/check': () => json(200, check),
      'GET /api/credit/approvers': () => json(200, [{ id: 'o1', name: 'Owner One' }]),
      'POST /api/terminal/sales': (body) =>
        (body as { credit_override?: unknown }).credit_override
          ? apiError(401, 'authentication_failed', "That's not correct. Please try again.")
          : apiError(409, 'credit_limit_exceeded', 'Over the limit. An owner can allow it.', {
              can_override: true,
            }),
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Credit' }));
    await userEvent.selectOptions(screen.getByLabelText(/Customer/), 'c1');
    await userEvent.click(screen.getByRole('button', { name: 'Complete sale' }));
    const dialog = await screen.findByRole('dialog', { name: 'An owner must allow this bill' });
    await userEvent.type(within(dialog).getByLabelText("Owner's password"), 'nope');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Allow this bill' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent("That's not correct");
    expect(screen.queryByRole('heading', { name: 'Sale recorded' })).not.toBeInTheDocument();
  });
});

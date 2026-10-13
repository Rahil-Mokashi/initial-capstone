import { screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { json } from '@/test/mockApi';

beforeEach(() => session.set(null));
afterEach(() => {
  vi.unstubAllGlobals();
  delete window.pperp;
});

const greeting = /Good (morning|afternoon|evening)/;

describe('Today, by role', () => {
  it('shows the owner the checks summary, day status and credit outstanding', async () => {
    await openAs(
      ['check.view', 'shift.view', 'credit.view'],
      '/',
      greeting,
      {
        'GET /api/checks': () =>
          json(200, {
            day: '2026-10-12',
            summary: { total: 18, passed: 17, warned: 0, failed: 1 },
            results: [
              {
                id: 'r1',
                key: 'k',
                scope_type: 'day',
                scope_id: 'd',
                business_date: '2026-10-12',
                area: 'Cash',
                sentence: 'Shift 1: payment modes add up to the shift total',
                expected: '100.00',
                actual: '90.00',
                difference: '-10.00',
                unit: 'rs',
                status: 'fail',
                links: [],
                run_at: '2026-10-12T10:00:00Z',
                explanations: [],
              },
            ],
          }),
        'GET /api/dashboard/summary': () =>
          json(200, { open_shifts_count: 1, open_shift_labels: ['Morning'] }),
        'GET /api/credit/chase': () =>
          json(200, [
            {
              customer_id: 'c2',
              name: 'B',
              reason: 'promise',
              detail: 'Promised to pay today',
              promised_date: '2026-10-12',
              promised_amount: '5000.00',
              balance: '9000.00',
              follow_up_id: 'f1',
            },
          ]),
        'GET /api/credit/accounts': () =>
          json(200, [
            {
              customer_id: 'c1',
              customer: 'A',
              credit_limit: '1000.00',
              outstanding: '0.10',
              overdue: false,
              payment_due_days: 30,
            },
            {
              customer_id: 'c2',
              customer: 'B',
              credit_limit: '1000.00',
              outstanding: '0.20',
              overdue: true,
              payment_due_days: 30,
            },
          ]),
      },
      { role: 'OWNER' },
    );
    expect(await screen.findByText('17 of 18 checks passed')).toBeInTheDocument();
    expect(screen.getByText(/Shift 1: payment modes add up/)).toBeInTheDocument();
    expect(await screen.findByText('Morning shift open')).toBeInTheDocument();
    expect(await screen.findByText('₹0.30')).toBeInTheDocument(); // exact sum, no 0.30000000000000004
    expect(screen.getByText('2 credit customers, 1 overdue')).toBeInTheDocument();
    expect(await screen.findByText(/Promised to pay today/)).toBeInTheDocument(); // the promised-date reminder
  });

  it('shows the cashier only the shift entry list, in order, in the staff words', async () => {
    await openAs(
      ['shift.manage', 'sale.manage', 'expense.manage', 'reconciliation.manage'],
      '/',
      greeting,
      {},
      { role: 'DATA_ENTRY' },
    );
    const steps = within(await screen.findByRole('region', { name: /Shift entry/ })).getAllByRole(
      'listitem',
    );
    expect(
      steps.map(
        (li) => /\d(.*?)(Bill|Closing|Totals|Tea|Cash handed)/.exec(li.textContent ?? '')?.[1],
      ),
    ).toEqual([
      'Nozzle readings',
      'Credit bills',
      'Card, DTP Card, Phone Pay, PTM',
      'Expenses',
      'Advance, Final and bank deposits',
    ]);
    expect(screen.getByText(/Card, DTP Card, Phone Pay, PTM/)).toBeInTheDocument();
    expect(screen.getByText(/Advance, Final and bank deposits/)).toBeInTheDocument();
    expect(screen.queryByText('Sales Trend')).not.toBeInTheDocument();
    expect(screen.queryByText('Checks today')).not.toBeInTheDocument();
  });

  it('hides masters from the cashier menu but keeps the screens they work in', async () => {
    await openAs(
      [
        'shift.view',
        'shift.manage',
        'sale.view',
        'sale.manage',
        'employee.view',
        'fuel_price.view',
        'nozzle.view',
        'credit.view',
        'expense.view',
        'reconciliation.view',
      ],
      '/',
      greeting,
      {},
      { role: 'DATA_ENTRY' },
    );
    const nav = await screen.findByRole('navigation', { name: 'Main' });
    expect(nav).toHaveTextContent('Shifts');
    expect(nav).toHaveTextContent('Expenses');
    expect(nav).not.toHaveTextContent('Employees');
    expect(nav).not.toHaveTextContent('Fuel Prices');
    expect(nav).not.toHaveTextContent('Soon');
    expect(screen.getByRole('link', { name: 'Today' })).toBeInTheDocument();
  });
});

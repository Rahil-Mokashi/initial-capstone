import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { json } from '@/test/mockApi';

beforeEach(() => session.set(null));
afterEach(() => {
  vi.unstubAllGlobals();
  delete window.pperp;
});

const shift = (n: number, sale: string, over: Record<string, unknown> = {}) => ({
  number: n,
  shift_id: `s${n}`,
  litres_by_tank: { t1: n === 1 ? '995.000' : '500.000', t2: '0.000' },
  oil_rs: n === 1 ? '500.00' : '1750.00',
  total_sale: sale,
  lines: [
    ['CreditSale', '20000.00'],
    ['CARD', '0.00'],
    ['DTP Card', '10000.00'],
    ['PHONE PAY', '5000.00'],
    ['PTM', '30000.00'],
    ['Expenses', '1050.00'],
    ['Advance', '40000.00'],
    ['Final', '38950.00'],
  ],
  lines_total: '145000.00',
  cash_in_hand: '8950.00',
  ...over,
});

const report = (second: Record<string, unknown> = {}) => ({
  day: '2026-10-12',
  style: 'classic',
  html: '<div>two sides</div>',
  report: {
    tanks: [
      { tank_id: 't1', code: 'MS-22' },
      { tank_id: 't2', code: 'HSD-16' },
    ],
    shifts: [shift(1, '145000.00'), shift(2, '87750.00', { lines_total: '87750.00', ...second })],
    opening: { t1: '35485.000', t2: '8000.000' },
    purchase: { t1: '23000.000', t2: '0.000' },
    testing: { t1: '5.000', t2: '0.000' },
    total_stock: { t1: '56990.000', t2: '7500.000' },
    closing: { t1: '56950.000', t2: null },
    plus_minus: { t1: '-40.000', t2: null },
    total_rs: '230500.00',
  },
});

const checks = {
  day: '2026-10-12',
  summary: { total: 18, passed: 18, warned: 0, failed: 0 },
  results: [],
};

describe('Daily Report screen', () => {
  it('shows the Sale Details grid in the old order with Indian grouping and the Total Rs', async () => {
    await openAs(['daily_report.view', 'check.view'], '/daily-report', 'Daily Report', {
      'GET /api/daily-report': () => json(200, report()),
      'GET /api/checks': () => json(200, checks),
    });
    const grid = await screen.findByRole('table');
    const rowLabels = within(grid)
      .getAllByRole('rowheader')
      .map((h) => h.textContent);
    expect(rowLabels).toEqual([
      'O/S',
      'Purchase',
      'Shift1',
      'Shift2',
      'Testing',
      'Total Stock',
      '(+/-)',
      'Closing Stock',
      'Total Rs',
    ]);
    expect(within(grid).getByText('MS-22')).toBeInTheDocument();
    expect(within(grid).getByText('35,485')).toBeInTheDocument();
    expect(within(grid).getByText('-40')).toBeInTheDocument();
    expect(within(grid).getByText('₹2,30,500.00')).toBeInTheDocument();
    expect(screen.getByText(/18 of 18 checks passed/)).toBeInTheDocument();
  });

  it('says plainly when a shift total does not equal its Total Sale', async () => {
    await openAs(['daily_report.view', 'check.view'], '/daily-report', 'Daily Report', {
      'GET /api/daily-report': () => json(200, report({ lines_total: '86750.00' })),
      'GET /api/checks': () => json(200, checks),
    });
    expect(await screen.findByText(/Does not equal Total Sale ₹87,750.00/)).toBeInTheDocument();
    expect(screen.getAllByText("Equals the shift's Total Sale")).toHaveLength(1);
  });

  it('hands the printable HTML to the print preview', async () => {
    const preview = vi.fn(async (html: string) => ({ ok: html.length > 0 }));
    window.pperp = { print: { preview } } as unknown as typeof window.pperp;
    await openAs(['daily_report.view'], '/daily-report', 'Daily Report', {
      'GET /api/daily-report': () => json(200, report()),
      'GET /api/checks': () =>
        json(403, { error: { code: 'permission_denied', message: 'no', details: {} } }),
    });
    await userEvent.click(await screen.findByRole('button', { name: /Print preview/ }));
    await waitFor(() => expect(preview).toHaveBeenCalled());
    expect(preview.mock.calls[0]![0]).toBe('<div>two sides</div>');
  });
});

describe('Oil / Lubricants screen', () => {
  const item = {
    id: 'i1',
    name: 'HP Racer 1L',
    pack_size: '1 ltr',
    default_rate: '250.00',
    stock: '27.000',
  };

  it('lists items with stock and rate, and lets a manager add one', async () => {
    const api = await openAs(
      ['lubricant.view', 'lubricant.manage'],
      '/lubricants',
      'Oil and Lubricants',
      {
        'GET /api/lubricants': () => json(200, [item]),
        'POST /api/lubricants': () =>
          json(201, { ...item, id: 'i2', name: 'Milcy', stock: '0.000' }),
      },
    );
    expect(await screen.findByText('HP Racer 1L')).toBeInTheDocument();
    expect(screen.getByText('27 in stock')).toBeInTheDocument();
    expect(screen.getByText(/Rate ₹250.00/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Add oil item' }));
    const d = screen.getByRole('dialog');
    await userEvent.type(within(d).getByLabelText('Name'), 'Milcy');
    await userEvent.type(within(d).getByLabelText('Selling rate (Rs)'), '1500');
    await userEvent.click(within(d).getByRole('button', { name: 'Add item' }));
    await waitFor(() => expect(api.calls.some((c) => c.key === 'POST /api/lubricants')).toBe(true));
    expect(api.calls.find((c) => c.key === 'POST /api/lubricants')!.body).toMatchObject({
      name: 'Milcy',
      default_rate: '1500',
    });
  });

  it('shows no add or record buttons to a view-only user', async () => {
    await openAs(['lubricant.view'], '/lubricants', 'Oil and Lubricants', {
      'GET /api/lubricants': () => json(200, [item]),
    });
    await screen.findByText('HP Racer 1L');
    expect(screen.queryByRole('button', { name: 'Add oil item' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Record' })).not.toBeInTheDocument();
  });
});

describe('Bowser Van screen', () => {
  const day = {
    day: '2026-10-12',
    day_report: {
      stock_lines: [
        { label: 'Opening Stock', litres: '1000.000', rupees: '90000.00' },
        { label: 'Stock Transfer', litres: '200.000', rupees: '18000.00' },
      ],
      stock_litres: '1200.000',
      stock_rupees: '108000.00',
      bills: [
        {
          id: 'b1',
          bill_no: 'B1',
          customer: 'Beta Concrete',
          quantity: '150.000',
          rate: '95.00',
          amount: '14250.00',
          transport: '500.00',
          total: '14750.00',
        },
      ],
      bills_qty: '150.000',
      bills_amount: '14250.00',
      bills_transport: '500.00',
      bills_total: '14750.00',
      closing_litres: '1050.000',
      closing_rupees: '94500.00',
      meter: { start_reading: '1000.000', testing: '0.000', end_reading: '1150.000' },
      meter_net: '150.000',
    },
  };

  it('shows A, B and C like the old report and says the meter equals the bills', async () => {
    await openAs(['bowser.view', 'bowser.manage'], '/bowser', 'Bowser Van', {
      'GET /api/bowser/day': () => json(200, day),
    });
    expect(await screen.findByText('A] Internal stock')).toBeInTheDocument();
    expect(screen.getAllByText('Stock Transfer')).toHaveLength(2); // the button and the row of table A
    expect(screen.getByText('₹1,08,000.00')).toBeInTheDocument();
    expect(screen.getByText('B] Bills')).toBeInTheDocument();
    expect(screen.getByText('Beta Concrete')).toBeInTheDocument();
    expect(screen.getByText('C] Bowser meter')).toBeInTheDocument();
    expect(screen.getByText('Net Sale equals the litres on the bills')).toBeInTheDocument();
  });

  it('warns with both figures when the meter disagrees with the bills', async () => {
    const bad = { ...day, day_report: { ...day.day_report, meter_net: '140.000' } };
    await openAs(['bowser.view'], '/bowser', 'Bowser Van', {
      'GET /api/bowser/day': () => json(200, bad),
    });
    expect(await screen.findByText('Net Sale 140 L, bills 150 L')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add bill' })).not.toBeInTheDocument();
  });
});

describe('Payment mode totals screen', () => {
  it('lists the modes with the old report wording and saves one total', async () => {
    const rows = [
      { tender_id: 'a', name: 'Card', label: 'CARD', amount: null, reference: null },
      { tender_id: 'b', name: 'Paytm', label: 'PTM', amount: '30000.00', reference: 'slip' },
    ];
    const api = await openAs(
      ['reconciliation.manage', 'reconciliation.view', 'shift.view'],
      '/shift-totals',
      /Card, DTP Card, Phone Pay and PTM totals/,
      {
        'GET /api/shifts': () =>
          json(200, [
            { id: 's1', shift_date: '2026-10-12', shift_label: 'Morning', status: 'open' },
          ]),
        'GET /api/shift-totals/s1': () => json(200, rows),
        'PUT /api/shift-totals/s1/a': () => json(200, rows),
        'GET /api/sales/options': () =>
          json(200, {
            can_pick_freely: true,
            customers: [],
            employees: [],
            nozzles: [],
            shifts: [],
          }),
        'GET /api/lookups/fuels': () => json(200, []),
      },
    );
    expect(await screen.findByText('CARD')).toBeInTheDocument();
    expect(screen.getByText('Saved: ₹30,000.00')).toBeInTheDocument();
    const form = screen.getByRole('form', { name: 'CARD' });
    await userEvent.type(within(form).getByLabelText('CARD total (Rs)'), '1234.50');
    await userEvent.click(within(form).getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(api.calls.some((c) => c.key === 'PUT /api/shift-totals/s1/a')).toBe(true),
    );
    expect(api.calls.find((c) => c.key === 'PUT /api/shift-totals/s1/a')!.body).toMatchObject({
      amount: '1234.50',
    });
  });
});

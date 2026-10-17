import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { json } from '@/test/mockApi';

const PERMS = ['sale.view', 'sale.manage'];
const nozzle = (over: Record<string, unknown> = {}) => ({
  id: 'n1',
  code: 'N1',
  fuel_type: 'Petrol',
  rate_per_liter: '103.50',
  ...over,
});
const manager = (over: Record<string, unknown> = {}) => ({
  can_pick_freely: true,
  shifts: [{ id: 's1', label: '2026-10-11 Morning' }],
  employees: [{ id: 'e1', label: 'EMP-0001 - Ravi Kumar' }],
  nozzles: [nozzle(), nozzle({ id: 'n2', code: 'N2', fuel_type: 'Diesel', rate_per_liter: null })],
  customers: [{ id: 'c1', label: 'ACME' }],
  my_assignment: null,
  ...over,
});
const sale = {
  id: 'x1',
  receipt_number: 'R-0001',
  sale_at: '2026-10-11T08:30:00Z',
  fuel_type: 'Petrol',
  nozzle_id: 'n1',
  nozzle: 'N1',
  customer: null,
  quantity: '4.831',
  rate_per_liter: '103.50',
  amount: '500.00',
  payment_method: 'cash',
  status: 'completed',
  payment_id: 'p1',
  payment_status: 'success',
};
const base = (ctx = manager()) => ({
  'GET /api/terminal/context': () => json(200, ctx),
  'GET /api/sales': () => json(200, { total: 1, items: [sale] }),
});

beforeEach(() => session.set(null));
afterEach(() => vi.unstubAllGlobals());

describe('terminal', () => {
  it('previews volume and total exactly, in rupee mode and in litres mode', async () => {
    await openAs(PERMS, '/terminal', 'Terminal', base());
    expect(await screen.findByText(/Volume: 4.83 L\s+Total: ₹500.00/)).toBeInTheDocument(); // 500 / 103.50
    await userEvent.click(screen.getByRole('button', { name: 'Litres' }));
    const box = screen.getByLabelText('Quantity (L)');
    await userEvent.clear(box);
    await userEvent.type(box, '12.5');
    expect(await screen.findByText(/Volume: 12.5 L\s+Total: ₹1,293.75/)).toBeInTheDocument(); // 12.5 * 103.50
  });

  it('quick amounts set the amount and switch back to rupee mode', async () => {
    await openAs(PERMS, '/terminal', 'Terminal', base());
    await userEvent.click(await screen.findByRole('button', { name: 'Litres' }));
    await userEvent.click(screen.getByRole('button', { name: '₹1000' }));
    expect(screen.getByLabelText('Amount (₹)')).toHaveValue('1000');
    expect(screen.getByRole('button', { name: '₹ Amount' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('a nozzle whose fuel has no price says so and refuses to sell', async () => {
    const api = await openAs(PERMS, '/terminal', 'Terminal', base());
    await userEvent.click(await screen.findByRole('button', { name: 'N2 Diesel' }));
    expect(await screen.findByText('This fuel has no selling price set yet.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Complete sale' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('no selling price');
    expect(api.calls.some((c) => c.key === 'POST /api/terminal/sales')).toBe(false);
  });

  it('the office desk offers credit only, needs a vehicle number, and creates a new customer on the spot', async () => {
    const api = await openAs(PERMS, '/terminal', 'Terminal', {
      ...base(),
      'POST /api/customers': () => json(201, { id: 'c9', name: 'Ravi Transport' }),
      'POST /api/terminal/sales': () => json(201, { ...sale, payment_method: 'credit' }),
    });
    expect(await screen.findByRole('button', { name: 'Credit' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'DTP Card' })).toBeInTheDocument();
    for (const m of ['Cash', 'Upi', 'Card']) expect(screen.queryByRole('button', { name: m })).toBeNull();
    await userEvent.selectOptions(screen.getByLabelText('Customer (required for credit)'), '+ New customer');
    await userEvent.type(screen.getByLabelText('New customer name'), 'Ravi Transport');
    await userEvent.click(screen.getByRole('button', { name: 'Complete sale' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Enter the vehicle number');
    await userEvent.type(screen.getByLabelText('Vehicle number'), 'MH 12 AB 1234');
    await userEvent.click(screen.getByRole('button', { name: 'Complete sale' }));
    expect(await screen.findByRole('heading', { name: 'Sale recorded' })).toBeInTheDocument();
    expect(api.calls.find((c) => c.key === 'POST /api/customers')?.body).toEqual({ name: 'Ravi Transport' });
    expect(api.calls.find((c) => c.key === 'POST /api/terminal/sales')?.body).toEqual({
      mode: 'amount',
      value: '500',
      payment_method: 'credit',
      customer_id: 'c9',
      vehicle_number: 'MH 12 AB 1234',
      shift_id: 's1',
      employee_id: 'e1',
      nozzle_id: 'n1',
    });
    expect(screen.getByText(/Receipt R-0001/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Print receipt' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'New sale' }));
    expect(await screen.findByRole('button', { name: 'Complete sale' })).toBeInTheDocument();
  });

  it('a credit sale without a customer is stopped before it is sent', async () => {
    const api = await openAs(PERMS, '/terminal', 'Terminal', base());
    await userEvent.type(await screen.findByLabelText('Vehicle number'), 'MH 12 AB 1234');
    await userEvent.click(screen.getByRole('button', { name: 'Complete sale' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Choose the customer');
    expect(api.calls.some((c) => c.key === 'POST /api/terminal/sales')).toBe(false);
    expect(screen.getByLabelText('Amount (₹)')).toHaveValue('500');
  });

  it('an attendant sees their own nozzle and sends no shift or nozzle choice', async () => {
    const api = await openAs(PERMS, '/terminal', 'Terminal', {
      ...base(
        manager({
          can_pick_freely: false,
          shifts: [],
          employees: [],
          nozzles: [],
          my_assignment: { shift_id: 's1', employee_id: 'e1', nozzle: nozzle() },
        }),
      ),
      'POST /api/terminal/sales': () => json(201, sale),
    });
    expect(
      await screen.findByText(/Selling from your current assignment: N1 - Petrol/),
    ).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('Vehicle number'), 'MH12AB1234');
    await userEvent.click(screen.getByRole('button', { name: 'Complete sale' }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/terminal/sales')?.body).toEqual({
        mode: 'amount',
        value: '500',
        payment_method: 'cash',
        vehicle_number: 'MH12AB1234',
      }),
    );
  });

  it('an attendant with no assignment cannot submit', async () => {
    await openAs(
      PERMS,
      '/terminal',
      'Terminal',
      base(manager({ can_pick_freely: false, nozzles: [], shifts: [], employees: [] })),
    );
    expect(
      await screen.findByText(/no active nozzle assignment - ask a supervisor/),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Complete sale' })).toBeDisabled();
  });
});

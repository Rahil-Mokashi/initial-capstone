import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { apiError, json } from '@/test/mockApi';

const VIEW = ['sale.view'];
const MANAGE = ['sale.view', 'sale.manage'];
const sale = (over: Record<string, unknown> = {}) => ({
  id: 'x1',
  receipt_number: 'R-0001',
  sale_at: '2026-10-11T08:30:00Z',
  fuel_type: 'Petrol',
  nozzle: 'N1',
  customer: null,
  quantity: '10.000',
  rate_per_liter: '100.00',
  amount: '1000.00',
  payment_method: 'cash',
  status: 'completed',
  payment_id: 'p1',
  payment_status: 'success',
  ...over,
});
const base = (items = [sale()], total = items.length) => ({
  'GET /api/sales': () => json(200, { total, items }),
  'GET /api/sales/today-by-fuel': () =>
    json(200, [{ fuel_type: 'Petrol', quantity: '10.00', amount: '1000.00' }]),
  'GET /api/customers': () => json(200, []),
  'GET /api/sales/options': () =>
    json(200, {
      can_pick_freely: true,
      shifts: [{ id: 's1', label: '2026-10-11 Morning' }],
      nozzles: [{ id: 'n1', label: 'N1' }],
      employees: [{ id: 'e1', label: 'EMP-0001 - Ravi Kumar' }],
      customers: [{ id: 'c1', label: 'ACME' }],
      my_assignment: null,
    }),
});

beforeEach(() => session.set(null));
afterEach(() => {
  vi.unstubAllGlobals();
  delete window.pperp;
});

describe('sales list', () => {
  it('shows today by fuel and the sales, with amounts as the server sent them', async () => {
    await openAs(VIEW, '/sales', 'Sales', base());
    const cards = await screen.findByRole('list', { name: "Today's revenue by fuel" });
    expect(within(cards).getByText('₹1,000.00')).toBeInTheDocument();
    expect(within(cards).getByText('10.00 L today')).toBeInTheDocument();
    expect(await screen.findByRole('cell', { name: 'R-0001' })).toBeInTheDocument();
    expect(screen.getByText('Showing 1-1 of 1')).toBeInTheDocument();
  });

  it('hides the revenue cards if they fail to load, and still shows the sales', async () => {
    await openAs(VIEW, '/sales', 'Sales', {
      ...base(),
      'GET /api/sales/today-by-fuel': () => apiError(500, 'internal_error', 'boom'),
    });
    expect(await screen.findByRole('cell', { name: 'R-0001' })).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: "Today's revenue by fuel" })).not.toBeInTheDocument();
  });

  it('pages 50 at a time and says where you are', async () => {
    const api = await openAs(VIEW, '/sales', 'Sales', {
      ...base(),
      'GET /api/sales': (_b, url) => {
        const offset = Number(url.searchParams.get('offset'));
        return json(200, {
          total: 120,
          items: [sale({ id: `x${offset}`, receipt_number: `R-${offset}` })],
        });
      },
    });
    expect(await screen.findByText('Showing 1-1 of 120')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Previous/ })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: /Next/ }));
    expect(await screen.findByText('Showing 51-51 of 120')).toBeInTheDocument();
    expect(api.calls.some((c) => c.key === 'GET /api/sales')).toBe(true);
  });

  it('view-only users get no record or cancel buttons', async () => {
    await openAs(VIEW, '/sales', 'Sales', base());
    await screen.findByRole('cell', { name: 'R-0001' });
    expect(screen.queryByRole('button', { name: /Record sale/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Cancel selected/ })).not.toBeInTheDocument();
  });
});

describe('selected sale actions', () => {
  it('actions stay disabled until a sale is selected', async () => {
    await openAs(MANAGE, '/sales', 'Sales', base());
    await screen.findByRole('cell', { name: 'R-0001' });
    expect(screen.getByRole('button', { name: 'Cancel selected' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Print receipt' })).toBeDisabled();
    await userEvent.click(screen.getByRole('radio', { name: 'Select sale R-0001' }));
    expect(screen.getByRole('button', { name: 'Cancel selected' })).toBeEnabled();
  });

  it('cancels with an optional reason, and marks a payment failed or refunds it', async () => {
    const api = await openAs(MANAGE, '/sales', 'Sales', {
      ...base(),
      'POST /api/sales/x1/cancel': () => json(200, sale({ status: 'cancelled' })),
      'POST /api/payments/p1/refund': () => json(200, { id: 'p1', status: 'refunded' }),
    });
    await userEvent.click(await screen.findByRole('radio', { name: 'Select sale R-0001' }));
    await userEvent.click(screen.getByRole('button', { name: 'Cancel selected' }));
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel sale' }),
    );
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/sales/x1/cancel')?.body).toEqual({
        reason: '',
      }),
    );
    await userEvent.click(screen.getByRole('radio', { name: 'Select sale R-0001' }));
    await userEvent.click(screen.getByRole('button', { name: 'Refund payment' }));
    await userEvent.type(
      within(screen.getByRole('dialog')).getByLabelText(/^Reason/),
      'customer returned',
    );
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Refund payment' }),
    );
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/payments/p1/refund')?.body).toEqual({
        reason: 'customer returned',
      }),
    );
  });

  it('opens the receipt in the desktop print preview and saves the PDF through the Save dialog', async () => {
    const preview = vi.fn(async () => ({ ok: true }));
    const save = vi.fn(async () => ({ ok: true, path: 'C:\\out\\receipt_R-0001.pdf' }));
    window.pperp = {
      apiBase: '',
      launchSecret: 's',
      files: { pickPath: async () => null, save },
      print: { preview },
    } as never;
    const pdfBytes = new Uint8Array([0x25, 0x50, 0x44, 0x46]); // %PDF
    await openAs(VIEW, '/sales', 'Sales', {
      ...base(),
      'GET /api/sales/x1/receipt': () =>
        json(200, { html: '<h3>Receipt R-0001</h3>', filename: 'receipt_R-0001.pdf' }),
    });
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    const original = fetchMock.getMockImplementation() as unknown as (
      input: RequestInfo | URL,
      init?: RequestInit,
    ) => Promise<Response>;
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) =>
      String(input).includes('/receipt.pdf')
        ? new Response(pdfBytes, { status: 200, headers: { 'Content-Type': 'application/pdf' } })
        : original(input, init),
    );
    await userEvent.click(await screen.findByRole('radio', { name: 'Select sale R-0001' }));
    await userEvent.click(screen.getByRole('button', { name: 'Print receipt' }));
    await waitFor(() => expect(preview).toHaveBeenCalledWith('<h3>Receipt R-0001</h3>', undefined));
    await userEvent.click(screen.getByRole('button', { name: 'Export PDF' }));
    await waitFor(() => expect(save).toHaveBeenCalledWith('receipt_R-0001.pdf', btoa('%PDF')));
    expect(await screen.findByText(/Saved to C:\\out\\receipt_R-0001.pdf/)).toBeInTheDocument();
  });
});

describe('record sale', () => {
  it('a manager picks shift, nozzle and attendant, and sends an exact quantity string', async () => {
    const api = await openAs(MANAGE, '/sales', 'Sales', {
      ...base(),
      'POST /api/sales': () => json(201, sale({ id: 'x2' })),
    });
    await userEvent.click(await screen.findByRole('button', { name: /Record sale/ }));
    const d = screen.getByRole('dialog');
    await userEvent.selectOptions(await within(d).findByLabelText('Shift'), 's1');
    await userEvent.selectOptions(within(d).getByLabelText('Nozzle'), 'n1');
    await userEvent.selectOptions(within(d).getByLabelText('Attendant'), 'e1');
    expect(within(d).getByLabelText('Quantity (L)')).toHaveValue('10');
    expect(within(d).queryByLabelText('UPI/Card reference')).not.toBeInTheDocument();
    await userEvent.selectOptions(within(d).getByLabelText('Payment method'), 'upi');
    await userEvent.type(within(d).getByLabelText('UPI/Card reference'), 'U123');
    await userEvent.click(within(d).getByRole('button', { name: 'Record sale' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.calls.find((c) => c.key === 'POST /api/sales')?.body).toEqual({
      shift_id: 's1',
      nozzle_id: 'n1',
      employee_id: 'e1',
      quantity: '10',
      payment_method: 'upi',
      reference_number: 'U123',
    });
  });

  it('shows the server rule (credit needs a customer) inside the dialog and keeps the form', async () => {
    await openAs(MANAGE, '/sales', 'Sales', {
      ...base(),
      'POST /api/sales': () =>
        apiError(409, 'conflict', 'A customer is required for a credit sale'),
    });
    await userEvent.click(await screen.findByRole('button', { name: /Record sale/ }));
    const d = screen.getByRole('dialog');
    await userEvent.selectOptions(await within(d).findByLabelText('Shift'), 's1');
    await userEvent.selectOptions(within(d).getByLabelText('Nozzle'), 'n1');
    await userEvent.selectOptions(within(d).getByLabelText('Attendant'), 'e1');
    await userEvent.selectOptions(within(d).getByLabelText('Payment method'), 'credit');
    expect(within(d).getByLabelText('Customer (required for credit)')).toBeInTheDocument();
    await userEvent.click(within(d).getByRole('button', { name: 'Record sale' }));
    expect(await within(d).findByRole('alert')).toHaveTextContent('customer is required');
    expect(within(d).getByLabelText('Quantity (L)')).toHaveValue('10');
  });

  it('an attendant sells from their own assignment and cannot if they have none', async () => {
    const api = await openAs(MANAGE, '/sales', 'Sales', {
      ...base(),
      'GET /api/sales/options': () =>
        json(200, {
          can_pick_freely: false,
          shifts: [],
          nozzles: [],
          employees: [],
          customers: [],
          my_assignment: { shift_id: 's1', nozzle_id: 'n1', employee_id: 'e1', nozzle: 'N1' },
        }),
      'POST /api/sales/mine': () => json(201, sale()),
    });
    await userEvent.click(await screen.findByRole('button', { name: /Record sale/ }));
    const d = screen.getByRole('dialog');
    expect(
      await within(d).findByText('Selling from your current assignment: N1'),
    ).toBeInTheDocument();
    expect(within(d).queryByLabelText('Shift')).not.toBeInTheDocument();
    await userEvent.click(within(d).getByRole('button', { name: 'Record sale' }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/sales/mine')?.body).toEqual({
        quantity: '10',
        payment_method: 'cash',
      }),
    );
  });

  it('without an assignment the attendant is told and nothing is sent', async () => {
    const api = await openAs(MANAGE, '/sales', 'Sales', {
      ...base(),
      'GET /api/sales/options': () =>
        json(200, {
          can_pick_freely: false,
          shifts: [],
          nozzles: [],
          employees: [],
          customers: [],
          my_assignment: null,
        }),
    });
    await userEvent.click(await screen.findByRole('button', { name: /Record sale/ }));
    const d = screen.getByRole('dialog');
    await within(d).findByText(/no active nozzle assignment - ask a supervisor/);
    await userEvent.click(within(d).getByRole('button', { name: 'Record sale' }));
    expect(await within(d).findByRole('alert')).toHaveTextContent(
      'You have no active nozzle assignment.',
    );
    expect(api.calls.some((c) => c.key.startsWith('POST /api/sales'))).toBe(false);
  });
});

describe('customers', () => {
  it('adds a customer and deactivates one without a reason', async () => {
    const api = await openAs(MANAGE, '/sales', 'Sales', {
      ...base(),
      'GET /api/customers': () =>
        json(200, [
          { id: 'c1', name: 'ACME', phone: '999', email: null, address: null, status: 'active' },
        ]),
      'POST /api/customers': () =>
        json(201, {
          id: 'c2',
          name: 'Beta',
          phone: null,
          email: null,
          address: null,
          status: 'active',
        }),
      'POST /api/customers/c1/status': () =>
        json(200, {
          id: 'c1',
          name: 'ACME',
          phone: '999',
          email: null,
          address: null,
          status: 'inactive',
        }),
    });
    await userEvent.click(await screen.findByRole('tab', { name: 'Customers' }));
    await userEvent.click(await screen.findByRole('button', { name: /Add customer/ }));
    let d = screen.getByRole('dialog');
    await userEvent.click(within(d).getByRole('button', { name: 'Save' }));
    expect(await within(d).findByText('Enter the customer name.')).toBeInTheDocument();
    await userEvent.type(within(d).getByLabelText('Name'), 'Beta');
    await userEvent.click(within(d).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.calls.find((c) => c.key === 'POST /api/customers')?.body).toEqual({ name: 'Beta' });
    await userEvent.click(screen.getByRole('button', { name: /Mark inactive - ACME/ }));
    d = screen.getByRole('dialog');
    await userEvent.click(within(d).getByRole('button', { name: 'Mark inactive' }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/customers/c1/status')?.body).toEqual({
        status: 'inactive',
        reason: '',
      }),
    );
  });
});

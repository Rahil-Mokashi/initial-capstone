import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { apiError, json } from '@/test/mockApi';

const MANAGE = ['procurement.view', 'procurement.manage'];
const po = (over: Record<string, unknown> = {}) => ({
  id: 'p1',
  po_number: 'PO-0001',
  supplier_id: 's1',
  supplier: 'Indian Oil',
  order_date: '2026-10-01',
  expected_delivery_date: null,
  status: 'placed',
  remarks: null,
  items: [
    {
      id: 'i1',
      fuel_id: 'f1',
      fuel_type: 'Petrol',
      quantity_ordered: '5000.000',
      rate_per_liter: '90.50',
    },
  ],
  total_quantity: '5000.000',
  ...over,
});
const delivery = (over: Record<string, unknown> = {}) => ({
  id: 'd1',
  purchase_order_id: 'p1',
  tank_id: 't1',
  tanker_number: 'MH12-1',
  driver_name: null,
  arrived_at: '2026-10-10T08:00:00Z',
  status: 'arrived',
  quality_notes: null,
  pre_dip_value: null,
  post_dip_value: null,
  quantity_received: null,
  rejection_reason: null,
  remarks: null,
  ...over,
});
const supplier = {
  id: 's1',
  name: 'Indian Oil',
  status: 'active',
  contact_person: null,
  phone: null,
  email: null,
  address: null,
  gst_number: null,
};
const base = () => ({
  'GET /api/suppliers': () => json(200, [supplier]),
  'GET /api/purchase-orders': () => json(200, [po()]),
  'GET /api/invoices': () => json(200, []),
  'GET /api/procurement/order-options': () =>
    json(200, {
      suppliers: [{ id: 's1', label: 'Indian Oil' }],
      fuels: [{ id: 'f1', fuel_type: 'Petrol' }],
    }),
  'GET /api/procurement/arrival-options': () =>
    json(200, {
      tanks: [{ id: 't1', label: 'T1 (Petrol)' }],
      employees: [{ id: 'e1', label: 'EMP-0001 - Ravi Kumar' }],
    }),
});

beforeEach(() => session.set(null));
afterEach(() => vi.unstubAllGlobals());

describe('procurement tabs', () => {
  it('opens on the tab named in the link and shows pending delivery cards', async () => {
    await openAs(MANAGE, '/procurement?tab=orders', 'Procurement', base());
    expect(await screen.findByRole('heading', { name: 'Pending Deliveries' })).toBeInTheDocument();
    expect(screen.getByText('No ETA set')).toBeInTheDocument();
    expect(screen.getByText(/Petrol - 5,000.000 L/)).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Purchase Orders' })).toHaveAttribute(
      'data-state',
      'active',
    );
  });

  it('the suppliers link lands on the suppliers tab; add and deactivate a supplier', async () => {
    const api = await openAs(MANAGE, '/procurement?tab=suppliers', 'Procurement', {
      ...base(),
      'POST /api/suppliers': () => json(201, { ...supplier, id: 's2', name: 'HP' }),
      'POST /api/suppliers/s1/status': () => json(200, { ...supplier, status: 'inactive' }),
    });
    expect(await screen.findByRole('cell', { name: 'Indian Oil' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Add supplier/ }));
    let d = screen.getByRole('dialog');
    await userEvent.click(within(d).getByRole('button', { name: 'Save' }));
    expect(await within(d).findByText('Enter the supplier name.')).toBeInTheDocument();
    await userEvent.type(within(d).getByLabelText('Name'), 'HP');
    await userEvent.click(within(d).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.calls.find((c) => c.key === 'POST /api/suppliers')?.body).toEqual({ name: 'HP' });
    await userEvent.click(screen.getByRole('button', { name: /Mark inactive - Indian Oil/ }));
    d = screen.getByRole('dialog');
    await userEvent.click(within(d).getByRole('button', { name: 'Mark inactive' }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/suppliers/s1/status')?.body).toEqual({
        status: 'inactive',
        reason: '',
      }),
    );
  });
});

describe('purchase orders', () => {
  it('needs an item before it creates the order, then sends exact decimal strings', async () => {
    const api = await openAs(MANAGE, '/procurement?tab=orders', 'Procurement', {
      ...base(),
      'POST /api/purchase-orders': () => json(201, po({ id: 'p2', po_number: 'PO-0002' })),
    });
    await userEvent.click(await screen.findByRole('button', { name: /Create purchase order/ }));
    const d = screen.getByRole('dialog');
    await userEvent.selectOptions(await within(d).findByLabelText('Supplier'), 's1');
    await userEvent.click(within(d).getByRole('button', { name: 'Create order' }));
    expect(await within(d).findByText('Add at least one item to the order.')).toBeInTheDocument();
    await userEvent.click(within(d).getByRole('button', { name: /Add item/ }));
    expect(within(d).getByRole('table', { name: 'Items on this order' })).toHaveTextContent(
      '1,000',
    );
    await userEvent.click(within(d).getByRole('button', { name: 'Create order' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    const body = api.calls.find((c) => c.key === 'POST /api/purchase-orders')?.body as {
      items: unknown[];
    };
    expect(body.items).toEqual([{ fuel_id: 'f1', quantity_ordered: '1000', rate_per_liter: '95' }]);
  });

  it('records a tanker arrival and cancels an order', async () => {
    const api = await openAs(MANAGE, '/procurement/orders/p1', 'PO-0001', {
      ...base(),
      'GET /api/purchase-orders/p1': () => json(200, po()),
      'GET /api/purchase-orders/p1/deliveries': () => json(200, []),
      'POST /api/purchase-orders/p1/deliveries': () => json(201, delivery()),
      'POST /api/purchase-orders/p1/cancel': () => json(200, po({ status: 'cancelled' })),
    });
    await userEvent.click(await screen.findByRole('button', { name: /Record delivery arrival/ }));
    const d = screen.getByRole('dialog');
    await userEvent.click(within(d).getByRole('button', { name: 'Record arrival' }));
    expect(await within(d).findByText('Choose a tank.')).toBeInTheDocument();
    await userEvent.selectOptions(await within(d).findByLabelText('Tank'), 't1');
    await userEvent.selectOptions(within(d).getByLabelText('Received by'), 'e1');
    await userEvent.type(within(d).getByLabelText('Tanker number'), 'MH12-1');
    await userEvent.click(within(d).getByRole('button', { name: 'Record arrival' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(
      api.calls.find((c) => c.key === 'POST /api/purchase-orders/p1/deliveries')?.body,
    ).toEqual({
      tank_id: 't1',
      received_by_employee_id: 'e1',
      tanker_number: 'MH12-1',
    });
    await userEvent.click(screen.getByRole('button', { name: 'Cancel order' }));
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel order' }),
    );
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/purchase-orders/p1/cancel')?.body).toEqual({
        reason: '',
      }),
    );
  });

  it('a delivered order offers neither arrival nor cancel', async () => {
    await openAs(MANAGE, '/procurement/orders/p1', 'PO-0001', {
      ...base(),
      'GET /api/purchase-orders/p1': () => json(200, po({ status: 'delivered' })),
      'GET /api/purchase-orders/p1/deliveries': () => json(200, []),
    });
    expect(await screen.findByRole('button', { name: /Record delivery arrival/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Cancel order' })).toBeDisabled();
  });
});

describe('delivery workflow', () => {
  it('only the step valid for the status is enabled, in order', async () => {
    let current = delivery();
    const api = await openAs(MANAGE, '/procurement/deliveries/d1', 'Tanker MH12-1', {
      ...base(),
      'GET /api/deliveries/d1': () => json(200, current),
      'POST /api/deliveries/d1/verify-documents': () => {
        current = delivery({ status: 'documents_verified' });
        return json(200, current);
      },
    });
    const docs = await screen.findByRole('button', { name: 'Verify documents' });
    expect(docs).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Verify quality' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Record pre-dip reading' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Record post-dip and unload' })).toBeDisabled();
    await userEvent.click(docs);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Verify quality' })).toBeEnabled(),
    );
    expect(api.calls.some((c) => c.key === 'POST /api/deliveries/d1/verify-documents')).toBe(true);
    expect(screen.getByRole('button', { name: 'Verify documents' })).toBeDisabled();
  });

  it('records the pre-dip with a three-place value and shows a server rule inside the dialog', async () => {
    const api = await openAs(MANAGE, '/procurement/deliveries/d1', 'Tanker MH12-1', {
      ...base(),
      'GET /api/deliveries/d1': () =>
        json(200, delivery({ status: 'quality_verified', pre_dip_value: '2500.500' })),
      'POST /api/deliveries/d1/post-dip': () =>
        apiError(422, 'rule_violation', 'post-dip reading cannot be less than the pre-dip reading'),
    });
    expect(await screen.findByRole('button', { name: 'Record pre-dip reading' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Record post-dip and unload' }));
    const d = screen.getByRole('dialog');
    await userEvent.type(within(d).getByLabelText('Dip value (L)'), '2000.1234');
    expect(within(d).getByLabelText('Dip value (L)')).toHaveValue('2000.123'); // 4th place refused
    await userEvent.click(within(d).getByRole('button', { name: 'Record post-dip and unload' }));
    expect(await within(d).findByRole('alert')).toHaveTextContent(
      'cannot be less than the pre-dip',
    );
    expect(api.calls.find((c) => c.key === 'POST /api/deliveries/d1/post-dip')?.body).toEqual({
      dip_value: '2000.123',
    });
  });

  it('rejects a delivery with an optional reason', async () => {
    const api = await openAs(MANAGE, '/procurement/deliveries/d1', 'Tanker MH12-1', {
      ...base(),
      'GET /api/deliveries/d1': () => json(200, delivery()),
      'POST /api/deliveries/d1/reject': () => json(200, delivery({ status: 'rejected' })),
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Reject delivery' }));
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Reject delivery' }),
    );
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/deliveries/d1/reject')?.body).toEqual({
        reason: '',
      }),
    );
  });
});

describe('invoices', () => {
  const inv = (over: Record<string, unknown> = {}) => ({
    id: 'v1',
    invoice_number: 'INV-1',
    supplier_id: 's1',
    supplier: 'Indian Oil',
    purchase_order_id: null,
    invoice_date: '2026-10-10',
    due_date: null,
    amount: '1000.00',
    status: 'pending',
    remarks: null,
    ...over,
  });

  it('records an invoice and refuses a third decimal in the amount', async () => {
    const api = await openAs(MANAGE, '/procurement?tab=invoices', 'Procurement', {
      ...base(),
      'POST /api/invoices': () => json(201, inv()),
    });
    await userEvent.click(await screen.findByRole('button', { name: /Record invoice/ }));
    const d = screen.getByRole('dialog');
    await userEvent.type(within(d).getByLabelText('Invoice number'), 'INV-1');
    await userEvent.selectOptions(await within(d).findByLabelText('Supplier'), 's1');
    await userEvent.type(within(d).getByLabelText('Amount'), '1000.505');
    expect(within(d).getByLabelText('Amount')).toHaveValue('1000.50');
    await userEvent.click(within(d).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.calls.find((c) => c.key === 'POST /api/invoices')?.body).toMatchObject({
      invoice_number: 'INV-1',
      supplier_id: 's1',
      amount: '1000.50',
    });
  });

  it('records a payment; a paid invoice cannot take another', async () => {
    const api = await openAs(MANAGE, '/procurement/invoices/v1', 'INV-1', {
      ...base(),
      'GET /api/invoices/v1': () => json(200, inv()),
      'GET /api/invoices/v1/payments': () => json(200, []),
      'POST /api/invoices/v1/payments': () =>
        json(201, {
          id: 'y1',
          amount: '400.00',
          payment_date: '2026-10-11',
          payment_method: 'Bank Transfer',
          reference: null,
          remarks: null,
        }),
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Record payment' }));
    const d = screen.getByRole('dialog');
    expect(within(d).getByLabelText('Method')).toHaveValue('Bank Transfer');
    await userEvent.type(within(d).getByLabelText('Amount'), '400');
    await userEvent.click(within(d).getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/invoices/v1/payments')?.body).toMatchObject(
        {
          amount: '400',
          payment_method: 'Bank Transfer',
        },
      ),
    );
  });

  it('a paid invoice disables Record payment', async () => {
    await openAs(MANAGE, '/procurement/invoices/v1', 'INV-1', {
      ...base(),
      'GET /api/invoices/v1': () => json(200, inv({ status: 'paid' })),
      'GET /api/invoices/v1/payments': () => json(200, []),
    });
    expect(await screen.findByRole('button', { name: 'Record payment' })).toBeDisabled();
  });

  it('view-only users get no create or record buttons', async () => {
    await openAs(['procurement.view'], '/procurement?tab=orders', 'Procurement', base());
    await screen.findByRole('heading', { name: 'Pending Deliveries' });
    expect(screen.queryByRole('button', { name: /Create purchase order/ })).not.toBeInTheDocument();
  });
});

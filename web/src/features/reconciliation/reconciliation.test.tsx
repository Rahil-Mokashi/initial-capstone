import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { apiError, json } from '@/test/mockApi';

const ALL = [
  'reconciliation.view',
  'reconciliation.manage',
  'reconciliation.approve',
  'shortage.view',
  'shortage.manage',
  'employee.view',
];
const recon = (over: Record<string, unknown> = {}) => ({
  id: 'r1',
  shift_id: 's1',
  shift: '2026-10-11 Morning',
  lines: [
    { tender: 'Cash', variance: '-100.00' },
    { tender: 'Card', variance: '0.00' },
  ],
  classification: 'approval_required',
  status: 'pending_approval',
  remarks: null,
  ...over,
});
const book = {
  shift_id: 's1',
  shift: '2026-10-11 Morning',
  opening_balance: '0.00',
  advance_amount: '500.00',
  final_amount: '2000.00',
  bank_deposits_total: '700.00',
  closing_cash_in_hand: '1800.00',
  recorded_by: 'manager1',
};
const base = () => ({
  'GET /api/reconciliation': () => json(200, [recon()]),
  'GET /api/cash-book': () => json(200, [book]),
  'GET /api/shortages': () =>
    json(200, [
      {
        id: 'h1',
        employee: 'Ravi Kumar',
        shift: '2026-10-11 Morning',
        tender: 'Cash',
        amount: '100.00',
        recovered: '40.00',
        outstanding: '60.00',
        status: 'Outstanding',
      },
    ]),
  'GET /api/shortages/options': () =>
    json(200, {
      unbooked_lines: [{ id: 'l1', label: '2026-10-11 Morning - Cash short 100.00' }],
      outstanding_shortages: [{ id: 'h1', label: 'Ravi Kumar - outstanding 60.00' }],
    }),
  'GET /api/shifts': () =>
    json(200, [
      {
        id: 's1',
        shift_date: '2026-10-11',
        shift_label: 'Morning',
        status: 'closed',
        opened_by: 'm',
        notes: null,
        start_time: null,
        end_time: null,
        reopen_reason: null,
      },
    ]),
  'GET /api/employees': () =>
    json(200, [
      {
        id: 'e1',
        employee_code: 'EMP-0001',
        first_name: 'Ravi',
        last_name: 'Kumar',
        contact_number: '1',
        email: null,
        designation: null,
        department: null,
        assigned_outlet: null,
        joining_date: '2026-01-01',
        exit_date: null,
        status: 'active',
        emergency_contact_name: null,
        emergency_contact_phone: null,
      },
    ]),
  'GET /api/reconciliation/expected': () =>
    json(200, [
      { tender_id: 't-card', tender: 'Card', expected: '250.00' },
      { tender_id: 't-cash', tender: 'Cash', expected: '1000.00' },
    ]),
});

beforeEach(() => session.set(null));
afterEach(() => vi.unstubAllGlobals());

describe('reconciliation list', () => {
  it('shows the signed variance per tender, the classification and the status; all three sections are on the page', async () => {
    await openAs(ALL, '/reconciliation', 'Shift Reconciliation', base());
    expect(await screen.findByText('Cash: -100.00, Card: 0.00')).toBeInTheDocument();
    expect(screen.getAllByText('Approval Required').length).toBeGreaterThan(0);
    expect(screen.getByRole('table', { name: 'Shift cash book' })).toHaveTextContent('₹1,800.00');
    expect(screen.getByRole('table', { name: 'Employee cash shortages' })).toHaveTextContent(
      'Ravi Kumar',
    );
  });

  it('approves the selected reconciliation with optional remarks', async () => {
    const api = await openAs(ALL, '/reconciliation', 'Shift Reconciliation', {
      ...base(),
      'POST /api/reconciliation/r1/approve': () => json(200, recon({ status: 'approved' })),
    });
    expect(await screen.findByRole('button', { name: 'Approve selected' })).toBeDisabled();
    await userEvent.click(screen.getByRole('radio', { name: /Select reconciliation/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Approve selected' }));
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Approve' }),
    );
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/reconciliation/r1/approve')?.body).toEqual({
        remarks: '',
      }),
    );
  });

  it('view-only users see everything and have no action buttons', async () => {
    await openAs(
      ['reconciliation.view', 'shortage.view'],
      '/reconciliation',
      'Shift Reconciliation',
      base(),
    );
    await screen.findByText('Cash: -100.00, Card: 0.00');
    for (const name of [
      /Reconcile shift/,
      /Approve selected/,
      /Record bank deposit/,
      /Record cash movements/,
      /Record shortage/,
      /Record recovery/,
    ]) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
    }
  });
});

describe('reconcile a shift', () => {
  it('builds one declared-amount box per tender with activity and requires each one', async () => {
    const api = await openAs(ALL, '/reconciliation', 'Shift Reconciliation', {
      ...base(),
      'POST /api/reconciliation': () => json(201, recon()),
    });
    await userEvent.click(await screen.findByRole('button', { name: /Reconcile shift/ }));
    const d = screen.getByRole('dialog');
    await userEvent.selectOptions(await within(d).findByLabelText('Shift'), 's1');
    const cash = await within(d).findByLabelText('Declared Cash (expected 1000.00)');
    const card = within(d).getByLabelText('Declared Card (expected 250.00)');
    await userEvent.type(cash, '900');
    await userEvent.click(within(d).getByRole('button', { name: 'Reconcile' }));
    expect(
      await within(d).findByText('Enter the declared amount (0 if none).'),
    ).toBeInTheDocument();
    expect(api.calls.some((c) => c.key === 'POST /api/reconciliation')).toBe(false);
    await userEvent.type(card, '0');
    await userEvent.click(within(d).getByRole('button', { name: 'Reconcile' }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/reconciliation')?.body).toEqual({
        shift_id: 's1',
        declared_amounts: { 't-cash': '900', 't-card': '0' },
      }),
    );
  });

  it('says so when the shift has no tender activity, and shows a server refusal inside the dialog', async () => {
    await openAs(ALL, '/reconciliation', 'Shift Reconciliation', {
      ...base(),
      'GET /api/reconciliation/expected': () => json(200, []),
      'POST /api/reconciliation': () =>
        apiError(409, 'conflict', 'This shift has already been reconciled'),
    });
    await userEvent.click(await screen.findByRole('button', { name: /Reconcile shift/ }));
    const d = screen.getByRole('dialog');
    await userEvent.selectOptions(await within(d).findByLabelText('Shift'), 's1');
    expect(
      await within(d).findByText('This shift has no reconcilable tender activity.'),
    ).toBeInTheDocument();
    await userEvent.click(within(d).getByRole('button', { name: 'Reconcile' }));
    expect(await within(d).findByRole('alert')).toHaveTextContent('already been reconciled');
  });
});

describe('cash book and shortages', () => {
  it('records cash movements and a bank deposit', async () => {
    const api = await openAs(ALL, '/reconciliation', 'Shift Reconciliation', {
      ...base(),
      'POST /api/cash-book/movements': () => json(201, { id: 'm1' }),
      'POST /api/cash-book/deposits': () => json(201, { id: 'd1' }),
    });
    await userEvent.click(await screen.findByRole('button', { name: /Record cash movements/ }));
    let d = screen.getByRole('dialog');
    await userEvent.selectOptions(await within(d).findByLabelText('Shift'), 's1');
    await userEvent.clear(within(d).getByLabelText('Advance handed over'));
    await userEvent.type(within(d).getByLabelText('Advance handed over'), '500');
    await userEvent.clear(within(d).getByLabelText('Final handed over'));
    await userEvent.type(within(d).getByLabelText('Final handed over'), '2000');
    await userEvent.click(within(d).getByRole('button', { name: 'Record' }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/cash-book/movements')?.body).toEqual({
        shift_id: 's1',
        advance_amount: '500',
        final_amount: '2000',
      }),
    );
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: /Record bank deposit/ }));
    d = screen.getByRole('dialog');
    await userEvent.selectOptions(await within(d).findByLabelText('Shift'), 's1');
    await userEvent.type(within(d).getByLabelText('Bank'), 'HDFC Bank');
    await userEvent.type(within(d).getByLabelText('Amount deposited'), '700');
    await userEvent.click(within(d).getByRole('button', { name: 'Record' }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/cash-book/deposits')?.body).toEqual({
        shift_id: 's1',
        bank_name: 'HDFC Bank',
        amount: '700',
      }),
    );
  });

  it('books a shortage against an employee and records a recovery', async () => {
    const api = await openAs(ALL, '/reconciliation', 'Shift Reconciliation', {
      ...base(),
      'POST /api/shortages': () => json(201, { id: 'h2' }),
      'POST /api/shortages/recoveries': () => json(201, { id: 'v1' }),
    });
    await userEvent.click(await screen.findByRole('button', { name: /Record shortage/ }));
    let d = screen.getByRole('dialog');
    await userEvent.click(within(d).getByRole('button', { name: 'Record' }));
    expect(await within(d).findByRole('alert')).toHaveTextContent(
      'Choose the reconciliation line.',
    );
    await userEvent.selectOptions(await within(d).findByLabelText('Reconciliation line'), 'l1');
    await userEvent.selectOptions(within(d).getByLabelText('Responsible employee'), 'e1');
    await userEvent.click(within(d).getByRole('button', { name: 'Record' }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/shortages')?.body).toEqual({
        shift_reconciliation_line_id: 'l1',
        employee_id: 'e1',
      }),
    );
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: /Record recovery/ }));
    d = screen.getByRole('dialog');
    await userEvent.selectOptions(await within(d).findByLabelText('Shortage'), 'h1');
    await userEvent.selectOptions(within(d).getByLabelText('Repaid into shift'), 's1');
    await userEvent.type(within(d).getByLabelText('Amount recovered'), '40.505');
    expect(within(d).getByLabelText('Amount recovered')).toHaveValue('40.50');
    await userEvent.click(within(d).getByRole('button', { name: 'Record' }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/shortages/recoveries')?.body).toEqual({
        employee_cash_shortage_id: 'h1',
        shift_id: 's1',
        amount: '40.50',
      }),
    );
  });

  it('a manager without shortage rights cannot book shortages', async () => {
    await openAs(
      ['reconciliation.view', 'reconciliation.manage', 'shortage.view'],
      '/reconciliation',
      'Shift Reconciliation',
      base(),
    );
    await screen.findByText('Cash: -100.00, Card: 0.00');
    expect(screen.queryByRole('button', { name: /Record shortage/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Record cash movements/ })).toBeInTheDocument();
  });
});

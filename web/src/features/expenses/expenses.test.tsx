import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { apiError, json } from '@/test/mockApi';

const ALL = ['expense.view', 'expense.manage', 'expense.approve'];
const exp = (over: Record<string, unknown> = {}) => ({
  id: 'x1',
  expense_date: '2026-10-11',
  category_id: 'k1',
  category: 'Tea & snacks',
  amount: '250.00',
  payment_method: 'cash',
  employee_id: 'e1',
  employee: 'Ravi Kumar',
  receipt_reference: null,
  description: null,
  status: 'pending',
  ...over,
});
const base = (rows = [exp()]) => ({
  'GET /api/expenses': () => json(200, rows),
  'GET /api/expense-categories': () =>
    json(200, [{ id: 'k1', name: 'Tea & snacks', status: 'active' }]),
  'GET /api/expenses/options': () =>
    json(200, {
      categories: [{ id: 'k1', label: 'Tea & snacks' }],
      employees: [{ id: 'e1', label: 'EMP-0001 - Ravi Kumar' }],
      shifts: [{ id: 's1', label: '2026-10-11 Morning' }],
    }),
});

beforeEach(() => session.set(null));
afterEach(() => vi.unstubAllGlobals());

describe('expenses', () => {
  it('lists expenses with money as sent and a status badge', async () => {
    await openAs(ALL, '/expenses', 'Expenses', base());
    expect(await screen.findByRole('cell', { name: '₹250.00' })).toBeInTheDocument();
    expect(screen.getByText('Pending')).toBeInTheDocument();
  });

  it('records an expense with Qt defaults (500, cash), never offers credit, and refuses a third decimal', async () => {
    const api = await openAs(ALL, '/expenses', 'Expenses', {
      ...base(),
      'POST /api/expenses': () => json(201, exp({ id: 'x2' })),
    });
    await userEvent.click(await screen.findByRole('button', { name: /Record expense/ }));
    const d = screen.getByRole('dialog');
    expect(within(d).getByLabelText('Amount')).toHaveValue('500');
    expect(within(d).queryByRole('option', { name: 'Credit' })).not.toBeInTheDocument();
    await userEvent.click(within(d).getByRole('button', { name: 'Record expense' }));
    expect(await within(d).findByText('Choose a category.')).toBeInTheDocument();
    await userEvent.selectOptions(await within(d).findByLabelText('Category'), 'k1');
    await userEvent.selectOptions(within(d).getByLabelText('Employee'), 'e1');
    await userEvent.selectOptions(within(d).getByLabelText('Shift'), 's1');
    await userEvent.clear(within(d).getByLabelText('Amount'));
    await userEvent.type(within(d).getByLabelText('Amount'), '12.345');
    expect(within(d).getByLabelText('Amount')).toHaveValue('12.34');
    await userEvent.click(within(d).getByRole('button', { name: 'Record expense' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.calls.find((c) => c.key === 'POST /api/expenses')?.body).toEqual({
      category_id: 'k1',
      amount: '12.34',
      payment_method: 'cash',
      employee_id: 'e1',
      shift_id: 's1',
    });
  });

  it('says so when there are no categories yet', async () => {
    await openAs(ALL, '/expenses', 'Expenses', {
      ...base(),
      'GET /api/expenses/options': () => json(200, { categories: [], employees: [], shifts: [] }),
    });
    await userEvent.click(await screen.findByRole('button', { name: /Record expense/ }));
    expect(await within(screen.getByRole('dialog')).findByRole('alert')).toHaveTextContent(
      'add one from the Categories tab',
    );
  });

  it('approver selects a row, approves with remarks, and rejects without a reason', async () => {
    const api = await openAs(ALL, '/expenses', 'Expenses', {
      ...base(),
      'POST /api/expenses/x1/approve': () => json(200, exp({ status: 'approved' })),
      'POST /api/expenses/x1/reject': () => json(200, exp({ status: 'rejected' })),
    });
    expect(await screen.findByRole('button', { name: 'Approve selected' })).toBeDisabled();
    await userEvent.click(screen.getByRole('radio', { name: /Select expense Tea/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Approve selected' }));
    await userEvent.type(within(screen.getByRole('dialog')).getByLabelText(/^Remarks/), 'ok');
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Approve' }),
    );
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/expenses/x1/approve')?.body).toEqual({
        remarks: 'ok',
      }),
    );
    await userEvent.click(screen.getByRole('radio', { name: /Select expense Tea/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Reject selected' }));
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Reject' }),
    );
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/expenses/x1/reject')?.body).toEqual({
        reason: '',
      }),
    );
  });

  it('shows a server refusal when deciding an expense twice', async () => {
    await openAs(ALL, '/expenses', 'Expenses', {
      ...base(),
      'POST /api/expenses/x1/approve': () =>
        apiError(409, 'conflict', 'Cannot approve an expense with status approved'),
    });
    await userEvent.click(await screen.findByRole('radio', { name: /Select expense Tea/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Approve selected' }));
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Approve' }),
    );
    expect(await within(screen.getByRole('dialog')).findByRole('alert')).toHaveTextContent(
      'Cannot approve',
    );
  });

  it('a requester without approve rights gets neither approve nor reject; a viewer gets no record button', async () => {
    await openAs(['expense.view', 'expense.manage'], '/expenses', 'Expenses', base());
    await screen.findByRole('cell', { name: '₹250.00' });
    expect(screen.queryByRole('button', { name: 'Approve selected' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Record expense/ })).toBeInTheDocument();
  });

  it('adds a category from the Categories tab', async () => {
    const api = await openAs(ALL, '/expenses', 'Expenses', {
      ...base(),
      'POST /api/expense-categories': () =>
        json(201, { id: 'k2', name: 'Cleaning', status: 'active' }),
    });
    await userEvent.click(await screen.findByRole('tab', { name: 'Categories' }));
    await userEvent.click(await screen.findByRole('button', { name: /Add category/ }));
    const d = screen.getByRole('dialog');
    await userEvent.click(within(d).getByRole('button', { name: 'Save' }));
    expect(await within(d).findByRole('alert')).toHaveTextContent('Enter the category name.');
    await userEvent.type(within(d).getByLabelText('Name'), 'Cleaning');
    await userEvent.click(within(d).getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/expense-categories')?.body).toEqual({
        name: 'Cleaning',
      }),
    );
  });
});

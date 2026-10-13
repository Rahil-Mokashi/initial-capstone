import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { json } from '@/test/mockApi';

beforeEach(() => session.set(null));
afterEach(() => vi.unstubAllGlobals());

const line = (over: Record<string, unknown> = {}) => ({
  id: 'l1',
  employee_id: 'e1',
  employee_name: 'Asha Patil',
  monthly_salary: '30000.00',
  days_in_month: 30,
  days_present: '28.0',
  paid_days: '28.0',
  gross: '28000.00',
  advance_deduction: '2000.00',
  shortage_deduction: '0.00',
  other_deduction: '100.00',
  other_note: null,
  net: '25900.00',
  payment: null,
  advance_outstanding: '5000.00',
  shortage_outstanding: '0.00',
  ...over,
});
const register = (status: string, over: Record<string, unknown> = {}) => ({
  run_id: 'r1',
  month: '2026-09',
  status,
  days_in_month: 30,
  leave_paid: 'off',
  holiday_paid: 'off',
  approved_by: status === 'draft' ? null : 'owner1',
  approved_at: null,
  lines: [line()],
  gross: '28000.00',
  advance: '2000.00',
  shortage: '0.00',
  other: '100.00',
  net: '25900.00',
  paid: '0.00',
  ...over,
});

describe('Payroll', () => {
  it('shows the register with days, earned, each deduction and net pay in rupees', async () => {
    await openAs(['payroll.view', 'payroll.manage'], '/payroll', 'Payroll', {
      'GET /api/payroll/register/2026-09': () => json(200, register('draft')),
    });
    await userEvent.clear(await screen.findByLabelText('Month'));
    await userEvent.type(screen.getByLabelText('Month'), '2026-09');
    const table = await screen.findByRole('table', { name: 'Salary register 2026-09' });
    const row = within(table).getByRole('row', { name: /Asha Patil/ });
    expect(within(row).getByText('28.0 of 30')).toBeInTheDocument();
    expect(within(row).getByText('₹25,900.00')).toBeInTheDocument();
    expect(screen.getByText('Draft: not approved yet')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve this month' })).not.toBeInTheDocument(); // owners only
    expect(within(row).getByRole('button', { name: 'Deductions' })).toBeInTheDocument();
    expect(within(row).queryByRole('button', { name: 'Mark paid' })).not.toBeInTheDocument(); // not before approval
  });

  it('lets an owner approve, and after approval offers Mark paid instead of Deductions', async () => {
    const api = await openAs(
      ['payroll.view', 'payroll.manage', 'payroll.approve'],
      '/payroll',
      'Payroll',
      {
        'GET /api/payroll/register/2026-09': () => json(200, register('draft')),
        'POST /api/payroll/runs/r1/approve': () => json(200, { id: 'r1' }),
      },
    );
    await userEvent.clear(await screen.findByLabelText('Month'));
    await userEvent.type(screen.getByLabelText('Month'), '2026-09');
    await userEvent.click(await screen.findByRole('button', { name: 'Approve this month' }));
    await waitFor(() =>
      expect(api.calls.some((c) => c.key === 'POST /api/payroll/runs/r1/approve')).toBe(true),
    );
  });

  it('after approval a person can mark a salary paid', async () => {
    await openAs(['payroll.view', 'payroll.manage'], '/payroll', 'Payroll', {
      'GET /api/payroll/register/2026-09': () => json(200, register('approved')),
    });
    await userEvent.clear(await screen.findByLabelText('Month'));
    await userEvent.type(screen.getByLabelText('Month'), '2026-09');
    expect(await screen.findByText('Approved by owner1')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Mark paid' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Deductions' })).not.toBeInTheDocument(); // locked once approved
  });
});

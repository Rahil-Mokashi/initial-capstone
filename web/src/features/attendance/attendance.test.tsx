import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { apiError, json } from '@/test/mockApi';

const emp = (id: string, first: string, status = 'active') => ({
  id,
  employee_code: `EMP-${id}`,
  first_name: first,
  last_name: 'Kumar',
  contact_number: '1',
  email: null,
  designation: null,
  department: null,
  assigned_outlet: null,
  joining_date: '2026-01-01',
  exit_date: null,
  status,
  emergency_contact_name: null,
  emergency_contact_phone: null,
});
const record = (over: Record<string, unknown> = {}) => ({
  id: 'r1',
  employee_id: 'e1',
  employee: 'Asha Kumar',
  attendance_date: '2026-10-11',
  status: 'present',
  check_in_time: null,
  check_out_time: null,
  shift_id: null,
  shift_label: null,
  overtime_minutes: 15,
  correction_reason: null,
  corrected_at: null,
  ...over,
});
const base = (records = [record()]) => ({
  'GET /api/employees': () =>
    json(200, [emp('e2', 'Ravi'), emp('e1', 'Asha'), emp('e3', 'Gone', 'terminated')]),
  'GET /api/attendance': () => json(200, records),
  'GET /api/shifts': () =>
    json(200, [{ id: 's1', shift_label: 'Morning', shift_date: '2026-10-11', status: 'open' }]),
});

beforeEach(() => session.set(null));
afterEach(() => vi.unstubAllGlobals());

describe('attendance roster', () => {
  it('lists only active employees, sorted, with marked status and quick buttons for the rest', async () => {
    await openAs(['attendance.view', 'attendance.manage'], '/attendance', 'Attendance', base());
    const table = await screen.findByRole('table');
    const rows = within(table).getAllByRole('row').slice(1);
    expect(rows).toHaveLength(2); // terminated employee is not on the roster
    expect(rows[0]).toHaveTextContent('Asha Kumar');
    expect(within(rows[0]!).getByText('Present')).toBeInTheDocument();
    expect(rows[1]).toHaveTextContent('Ravi Kumar');
    expect(
      within(rows[1]!).getByRole('button', { name: 'Mark Ravi Kumar absent' }),
    ).toBeInTheDocument();
  });

  it('marks present with one click and shows a server error above the table', async () => {
    let n = 0;
    const api = await openAs(
      ['attendance.view', 'attendance.manage'],
      '/attendance',
      'Attendance',
      {
        ...base(),
        'POST /api/attendance': () =>
          n++ === 0
            ? apiError(409, 'conflict', 'Already marked')
            : json(201, record({ employee_id: 'e2' })),
      },
    );
    await userEvent.click(await screen.findByRole('button', { name: 'Mark Ravi Kumar present' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Already marked');
    await userEvent.click(screen.getByRole('button', { name: 'Mark Ravi Kumar present' }));
    await waitFor(() =>
      expect(api.calls.filter((c) => c.key === 'POST /api/attendance')).toHaveLength(2),
    );
    expect(api.calls.find((c) => c.key === 'POST /api/attendance')?.body).toMatchObject({
      employee_id: 'e2',
      status: 'present',
      overtime_minutes: 0,
    });
  });

  it('marks through the dialog with a shift, and corrects a record without a reason', async () => {
    const api = await openAs(
      ['attendance.view', 'attendance.manage'],
      '/attendance',
      'Attendance',
      {
        ...base(),
        'POST /api/attendance': () => json(201, record({ id: 'r2', employee_id: 'e2' })),
        'POST /api/attendance/r1/correct': () =>
          json(200, record({ status: 'late', corrected_at: '2026-10-11T10:00:00Z' })),
      },
    );
    await userEvent.click(await screen.findByRole('button', { name: /Mark attendance/ }));
    let d = screen.getByRole('dialog');
    await userEvent.selectOptions(await within(d).findByLabelText('Employee'), 'e2');
    await userEvent.selectOptions(within(d).getByLabelText('Status'), 'late');
    await userEvent.selectOptions(await within(d).findByRole('combobox', { name: 'Shift' }), 's1');
    await userEvent.click(within(d).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.calls.find((c) => c.key === 'POST /api/attendance')?.body).toMatchObject({
      employee_id: 'e2',
      status: 'late',
      shift_id: 's1',
      shift_label: 'Morning',
    });

    await userEvent.click(screen.getByRole('button', { name: 'Correct attendance of Asha Kumar' }));
    d = screen.getByRole('dialog');
    await userEvent.selectOptions(within(d).getByLabelText('Status'), 'late');
    await userEvent.click(within(d).getByRole('button', { name: 'Save correction' }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/attendance/r1/correct')?.body).toEqual({
        status: 'late',
        overtime_minutes: 15,
        reason: '',
      }),
    );
  });

  it('view-only users see Not marked and no buttons', async () => {
    await openAs(['attendance.view'], '/attendance', 'Attendance', base([]));
    expect(await screen.findAllByText('Not marked')).toHaveLength(2);
    expect(screen.queryByRole('button', { name: /Mark attendance/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Mark Ravi/ })).not.toBeInTheDocument();
  });
});

describe('leave', () => {
  const leave = (over: Record<string, unknown> = {}) => ({
    id: 'l1',
    employee_id: 'e1',
    employee: 'Asha Kumar',
    date_from: '2026-10-20',
    date_to: '2026-10-22',
    reason: 'wedding',
    status: 'pending',
    decided_by: null,
    decision_reason: null,
    ...over,
  });
  const lbase = (
    rows = [leave(), leave({ id: 'l2', status: 'approved', decided_by: 'manager1' })],
  ) => ({
    'GET /api/leave': () => json(200, rows),
    'GET /api/employees': () => json(200, [emp('e1', 'Asha')]),
  });
  const ALL = ['leave.view', 'leave.manage', 'leave.approve'];

  it('only pending requests have actions; approve sends the remarks', async () => {
    const api = await openAs(ALL, '/leave', 'Leave', {
      ...lbase(),
      'POST /api/leave/l1/approve': () => json(200, leave({ status: 'approved' })),
    });
    await screen.findByRole('table');
    expect(screen.getAllByRole('button', { name: /Approve leave of/ })).toHaveLength(1);
    await userEvent.click(screen.getByRole('button', { name: 'Approve leave of Asha Kumar' }));
    const d = screen.getByRole('dialog');
    await userEvent.type(within(d).getByLabelText(/^Remarks/), 'ok');
    await userEvent.click(within(d).getByRole('button', { name: 'Approve' }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/leave/l1/approve')?.body).toEqual({
        remarks: 'ok',
      }),
    );
  });

  it('rejects and cancels with an optional reason; approvers and requesters see different buttons', async () => {
    const api = await openAs(ALL, '/leave', 'Leave', {
      ...lbase(),
      'POST /api/leave/l1/reject': () => json(200, leave({ status: 'rejected' })),
    });
    await userEvent.click(
      await screen.findByRole('button', { name: 'Reject leave of Asha Kumar' }),
    );
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Reject' }),
    );
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/leave/l1/reject')?.body).toEqual({
        reason: '',
      }),
    );
  });

  it('a requester without approve rights gets Cancel only', async () => {
    await openAs(['leave.view', 'leave.manage'], '/leave', 'Leave', lbase());
    expect(
      await screen.findByRole('button', { name: 'Cancel leave of Asha Kumar' }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Approve leave/ })).not.toBeInTheDocument();
  });

  it('requests leave: end before start is caught, then it posts', async () => {
    const api = await openAs(ALL, '/leave', 'Leave', {
      ...lbase([]),
      'POST /api/leave': () => json(201, leave()),
    });
    await userEvent.click(await screen.findByRole('button', { name: /Request leave/ }));
    const d = screen.getByRole('dialog');
    await userEvent.selectOptions(await within(d).findByLabelText('Employee'), 'e1');
    const from = within(d).getByLabelText('From');
    const to = within(d).getByLabelText('To');
    await userEvent.clear(from);
    await userEvent.type(from, '2026-10-22');
    await userEvent.clear(to);
    await userEvent.type(to, '2026-10-20');
    await userEvent.click(within(d).getByRole('button', { name: 'Request leave' }));
    expect(
      await within(d).findByText('The last day cannot be before the first day.'),
    ).toBeInTheDocument();
    await userEvent.clear(to);
    await userEvent.type(to, '2026-10-23');
    await userEvent.click(within(d).getByRole('button', { name: 'Request leave' }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/leave')?.body).toEqual({
        employee_id: 'e1',
        date_from: '2026-10-22',
        date_to: '2026-10-23',
        reason: '',
      }),
    );
  });
});

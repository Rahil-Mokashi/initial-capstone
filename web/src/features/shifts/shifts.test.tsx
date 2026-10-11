import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { apiError, json } from '@/test/mockApi';

const MANAGE = ['shift.view', 'shift.manage', 'shift.reopen'];
const shift = (over: Record<string, unknown> = {}) => ({
  id: 's1',
  shift_date: '2026-10-11',
  shift_label: 'Morning',
  status: 'open',
  opened_by: 'manager1',
  notes: null,
  start_time: null,
  end_time: null,
  reopen_reason: null,
  ...over,
});
const assignment = (over: Record<string, unknown> = {}) => ({
  id: 'a1',
  shift_id: 's1',
  employee_id: 'e1',
  employee: 'Ravi Kumar',
  nozzle_id: 'n1',
  nozzle: 'N1',
  opening_meter: '1000.000',
  closing_meter: null,
  testing_volume: '0.000',
  internal_consumption_volume: '0.000',
  status: 'active',
  start_time: null,
  end_time: null,
  ...over,
});
const base = (s = shift(), a = [assignment()]) => ({
  'GET /api/shifts': () => json(200, [s]),
  'GET /api/shifts/s1': () => json(200, s),
  'GET /api/shifts/s1/assignments': () => json(200, a),
  'GET /api/shifts/assign-options': () =>
    json(200, {
      employees: [{ id: 'e1', label: 'EMP-0001 - Ravi Kumar' }],
      nozzles: [{ id: 'n1', label: 'N1' }],
    }),
});

beforeEach(() => session.set(null));
afterEach(() => vi.unstubAllGlobals());

describe('shift list', () => {
  it('lists shifts and opens one with the default name and today', async () => {
    const api = await openAs(MANAGE, '/shifts', 'Shifts', {
      ...base(),
      'POST /api/shifts': () => json(201, shift({ id: 's2' })),
    });
    expect(await screen.findByRole('link', { name: /Oct 2026/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Open shift/ }));
    const d = screen.getByRole('dialog');
    expect(within(d).getByLabelText('Shift')).toHaveValue('Morning');
    await userEvent.click(within(d).getByRole('button', { name: 'Open' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    const body = api.calls.find((c) => c.key === 'POST /api/shifts')?.body as Record<
      string,
      string
    >;
    expect(body.shift_label).toBe('Morning');
    expect(body.shift_date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it('view-only users cannot open a shift', async () => {
    await openAs(['shift.view'], '/shifts', 'Shifts', base());
    await screen.findByRole('table', { name: 'Shifts' });
    expect(screen.queryByRole('button', { name: /Open shift/ })).not.toBeInTheDocument();
  });
});

describe('shift detail', () => {
  it('assigns a nozzle with the opening meter as an exact string', async () => {
    const api = await openAs(MANAGE, '/shifts/s1', 'Morning shift', {
      ...base(),
      'POST /api/shifts/s1/assignments': () => json(201, assignment({ id: 'a2' })),
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Assign nozzle' }));
    const d = screen.getByRole('dialog');
    await userEvent.click(within(d).getByRole('button', { name: 'Assign' }));
    expect(await within(d).findByText('Choose an employee.')).toBeInTheDocument();
    await userEvent.selectOptions(await within(d).findByLabelText('Employee'), 'e1');
    await userEvent.selectOptions(within(d).getByLabelText('Nozzle'), 'n1');
    await userEvent.clear(within(d).getByLabelText('Opening meter'));
    await userEvent.type(within(d).getByLabelText('Opening meter'), '1000.5');
    await userEvent.click(within(d).getByRole('button', { name: 'Assign' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.calls.find((c) => c.key === 'POST /api/shifts/s1/assignments')?.body).toEqual({
      employee_id: 'e1',
      nozzle_id: 'n1',
      opening_meter: '1000.5',
    });
  });

  it('completes an assignment with testing and internal consumption, and shows a server rule inside the dialog', async () => {
    let n = 0;
    const api = await openAs(MANAGE, '/shifts/s1', 'Morning shift', {
      ...base(),
      'POST /api/shift-assignments/a1/complete': () =>
        n++ === 0
          ? apiError(422, 'rule_violation', 'closing_meter cannot be less than opening_meter')
          : json(200, assignment({ status: 'completed', closing_meter: '1100.500' })),
    });
    await userEvent.click(await screen.findByRole('button', { name: /Complete/ }));
    const d = screen.getByRole('dialog');
    await userEvent.type(within(d).getByLabelText('Closing meter reading'), '900');
    await userEvent.click(within(d).getByRole('button', { name: 'Complete assignment' }));
    expect(await within(d).findByRole('alert')).toHaveTextContent(
      'cannot be less than opening_meter',
    );
    await userEvent.clear(within(d).getByLabelText('Closing meter reading'));
    await userEvent.type(within(d).getByLabelText('Closing meter reading'), '1100.5');
    await userEvent.clear(within(d).getByLabelText(/Litres tested/));
    await userEvent.type(within(d).getByLabelText(/Litres tested/), '5');
    await userEvent.click(within(d).getByRole('button', { name: 'Complete assignment' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    const last = api.calls.filter((c) => c.key === 'POST /api/shift-assignments/a1/complete').pop();
    expect(last?.body).toEqual({
      closing_meter: '1100.5',
      testing_volume: '5',
      internal_consumption_volume: '0',
    });
  });

  it('cancels an assignment without a reason, and closes the shift after a confirmation', async () => {
    const api = await openAs(MANAGE, '/shifts/s1', 'Morning shift', {
      ...base(),
      'POST /api/shift-assignments/a1/cancel': () => json(200, assignment({ status: 'cancelled' })),
      'POST /api/shifts/s1/close': () => json(200, shift({ status: 'closed' })),
    });
    await userEvent.click(await screen.findByRole('button', { name: /Cancel/ }));
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel assignment' }),
    );
    await waitFor(() =>
      expect(
        api.calls.find((c) => c.key === 'POST /api/shift-assignments/a1/cancel')?.body,
      ).toEqual({ reason: '' }),
    );
    await userEvent.click(screen.getByRole('button', { name: 'Close shift' }));
    expect(
      within(screen.getByRole('dialog')).getByText(/Active assignments must be completed/),
    ).toBeInTheDocument();
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Close shift' }),
    );
    await waitFor(() =>
      expect(api.calls.some((c) => c.key === 'POST /api/shifts/s1/close')).toBe(true),
    );
  });

  it('a closed shift offers Reopen (to those allowed) and no assignment actions', async () => {
    const api = await openAs(MANAGE, '/shifts/s1', 'Morning shift', {
      ...base(shift({ status: 'closed' }), [
        assignment({ status: 'completed', closing_meter: '1100.000' }),
      ]),
      'POST /api/shifts/s1/reopen': () => json(200, shift()),
    });
    expect(await screen.findByRole('button', { name: 'Assign nozzle' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Close shift' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: /Complete/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Reopen shift' }));
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Reopen shift' }),
    );
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/shifts/s1/reopen')?.body).toEqual({
        reason: '',
      }),
    );
  });

  it('without shift.reopen the reopen button stays disabled', async () => {
    await openAs(
      ['shift.view', 'shift.manage'],
      '/shifts/s1',
      'Morning shift',
      base(shift({ status: 'closed' }), []),
    );
    expect(await screen.findByRole('button', { name: 'Reopen shift' })).toBeDisabled();
  });
});

describe('my shift', () => {
  it('shows the current nozzle assignment', async () => {
    await openAs(['my_assignment.view'], '/my-shift', 'My Shift', {
      'GET /api/shifts/mine': () =>
        json(200, {
          shift_label: 'Morning',
          shift_date: '2026-10-11',
          nozzle: 'N1',
          fuel_type: 'Petrol',
          dispenser: 'D1',
          opening_meter: '1000.000',
          status: 'active',
        }),
    });
    expect(await screen.findByText('1,000.000')).toBeInTheDocument();
    expect(screen.getByText('Petrol')).toBeInTheDocument();
  });

  it('tells an unassigned attendant who to ask', async () => {
    await openAs(['my_assignment.view'], '/my-shift', 'My Shift', {
      'GET /api/shifts/mine': () => json(200, null),
    });
    expect(await screen.findByText(/Check with your shift supervisor/)).toBeInTheDocument();
  });
});

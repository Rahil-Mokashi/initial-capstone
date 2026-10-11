import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { apiError, json } from '@/test/mockApi';

const MANAGE = ['nozzle.view', 'nozzle.manage'];
const disp = (over: Record<string, unknown> = {}) => ({
  id: 'd1',
  code: 'D1',
  status: 'active',
  ...over,
});
const noz = (over: Record<string, unknown> = {}) => ({
  id: 'n1',
  code: 'N1',
  dispenser_id: 'd1',
  dispenser: 'D1',
  fuel_id: 'f1',
  fuel_type: 'Petrol',
  tank_id: null,
  status: 'active',
  ...over,
});
const base = () => ({
  'GET /api/dispensers': () => json(200, [disp()]),
  'GET /api/nozzles': () => json(200, [noz()]),
  'GET /api/nozzles/options': () =>
    json(200, {
      dispensers: [disp()],
      fuels: [{ id: 'f1', fuel_type: 'Petrol' }],
      tanks: [{ id: 't1', label: 'T1 (Petrol)' }],
    }),
});

beforeEach(() => session.set(null));
afterEach(() => vi.unstubAllGlobals());

describe('nozzle management', () => {
  it('shows dispensers, then nozzles on their own tab', async () => {
    await openAs(MANAGE, '/nozzles', 'Nozzle Management', base());
    expect(await screen.findByRole('cell', { name: 'D1' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', { name: 'Nozzles' }));
    expect(await screen.findByRole('cell', { name: 'N1' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'Petrol' })).toBeInTheDocument();
  });

  it('adds a dispenser, and shows a duplicate-code conflict inside the dialog', async () => {
    let n = 0;
    const api = await openAs(MANAGE, '/nozzles', 'Nozzle Management', {
      ...base(),
      'POST /api/dispensers': () =>
        n++ === 0
          ? apiError(409, 'conflict', "A dispenser with code 'D1' already exists")
          : json(201, disp({ id: 'd2', code: 'D2' })),
    });
    await userEvent.click(await screen.findByRole('button', { name: /Add dispenser/ }));
    const d = screen.getByRole('dialog');
    await userEvent.click(within(d).getByRole('button', { name: 'Save' }));
    expect(await within(d).findByText('Enter a code.')).toBeInTheDocument();
    await userEvent.type(within(d).getByLabelText('Code'), 'D1');
    await userEvent.click(within(d).getByRole('button', { name: 'Save' }));
    expect(await within(d).findByRole('alert')).toHaveTextContent('already exists');
    await userEvent.clear(within(d).getByLabelText('Code'));
    await userEvent.type(within(d).getByLabelText('Code'), 'D2');
    await userEvent.click(within(d).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.calls.filter((c) => c.key === 'POST /api/dispensers').map((c) => c.body)).toEqual([
      { code: 'D1' },
      { code: 'D2' },
    ]);
  });

  it('adds a nozzle with dispenser, fuel and the automatic tank', async () => {
    const api = await openAs(MANAGE, '/nozzles', 'Nozzle Management', {
      ...base(),
      'POST /api/nozzles': () => json(201, noz({ id: 'n2', code: 'N2' })),
    });
    await userEvent.click(screen.getByRole('tab', { name: 'Nozzles' }));
    await userEvent.click(await screen.findByRole('button', { name: /Add nozzle/ }));
    const d = screen.getByRole('dialog');
    await userEvent.type(within(d).getByLabelText('Code'), 'N2');
    await userEvent.selectOptions(await within(d).findByLabelText('Dispenser'), 'd1');
    await userEvent.selectOptions(within(d).getByLabelText('Fuel type'), 'f1');
    await userEvent.click(within(d).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.calls.find((c) => c.key === 'POST /api/nozzles')?.body).toEqual({
      code: 'N2',
      dispenser_id: 'd1',
      fuel_id: 'f1',
    });
  });

  it('changes a dispenser and a nozzle status without needing a reason', async () => {
    const api = await openAs(MANAGE, '/nozzles', 'Nozzle Management', {
      ...base(),
      'POST /api/dispensers/d1/status': () => json(200, disp({ status: 'inactive' })),
      'POST /api/nozzles/n1/status': () => json(200, noz({ status: 'maintenance' })),
    });
    await userEvent.click(
      await screen.findByRole('button', { name: /Mark inactive - dispenser D1/ }),
    );
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Mark inactive' }),
    );
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/dispensers/d1/status')?.body).toEqual({
        status: 'inactive',
        reason: '',
      }),
    );
    await userEvent.click(screen.getByRole('tab', { name: 'Nozzles' }));
    await userEvent.click(await screen.findByRole('button', { name: /Change status - nozzle N1/ }));
    const d = screen.getByRole('dialog');
    await userEvent.selectOptions(within(d).getByLabelText('New status'), 'maintenance');
    await userEvent.click(within(d).getByRole('button', { name: 'Change status' }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/nozzles/n1/status')?.body).toEqual({
        status: 'maintenance',
        reason: '',
      }),
    );
  });

  it('view-only users see the data but no add or edit controls', async () => {
    await openAs(['nozzle.view'], '/nozzles', 'Nozzle Management', base());
    await screen.findByRole('cell', { name: 'D1' });
    expect(screen.queryByRole('button', { name: /Add dispenser/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Mark inactive/ })).not.toBeInTheDocument();
  });
});

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { json } from '@/test/mockApi';

beforeEach(() => session.set(null));
afterEach(() => vi.unstubAllGlobals());

const line = (over: Record<string, unknown>) => ({
  nozzle_id: 'n1',
  code: 'N1',
  fuel: 'Petrol',
  tank: 'MS-22',
  opening: '1000.000',
  closed: false,
  closing: null,
  testing: '0.000',
  ...over,
});

describe('Shift Close', () => {
  it('shows each nozzle with its opening reading and sends only the closing readings that were typed', async () => {
    const api = await openAs(['shift.view', 'shift.manage'], '/shift-close', 'Shift Close', {
      'GET /api/shifts': () =>
        json(200, [{ id: 's1', shift_date: '2026-10-13', shift_label: 'Morning', status: 'open' }]),
      'GET /api/shift-close/s1': () =>
        json(200, [
          line({}),
          line({ nozzle_id: 'n2', code: 'N2', opening: null }),
          line({ nozzle_id: 'n3', code: 'N3', closed: true, closing: '250.000' }),
        ]),
      'POST /api/shift-close/s1': () => json(200, []),
    });
    const table = await screen.findByRole('table', { name: 'Nozzle readings' });
    expect(within(table).getAllByText('1,000')).toHaveLength(2); // opening = last closing
    expect(within(table).getByText('Closed')).toBeInTheDocument();
    await userEvent.type(within(table).getByLabelText('Closing for N1'), '1500');
    await userEvent.type(within(table).getByLabelText('Testing for N1'), '5');
    await userEvent.type(within(table).getByLabelText('Opening for N2'), '0'); // never closed: its opening is typed once
    await userEvent.type(within(table).getByLabelText('Closing for N2'), '200');
    await userEvent.click(screen.getByRole('button', { name: /Close 2 nozzle/ }));
    await waitFor(() =>
      expect(api.calls.some((c) => c.key === 'POST /api/shift-close/s1')).toBe(true),
    );
    expect(api.calls.find((c) => c.key === 'POST /api/shift-close/s1')!.body).toEqual({
      readings: [
        { nozzle_id: 'n1', closing: '1500', testing: '5', opening: null },
        { nozzle_id: 'n2', closing: '200', testing: '0', opening: '0' },
      ],
    });
  });

  it('tells the person to enter credit bills first, with links to the other steps', async () => {
    await openAs(['shift.view', 'shift.manage'], '/shift-close', 'Shift Close', {
      'GET /api/shifts': () =>
        json(200, [{ id: 's1', shift_date: '2026-10-13', shift_label: 'Morning', status: 'open' }]),
      'GET /api/shift-close/s1': () => json(200, [line({})]),
    });
    expect(await screen.findByRole('link', { name: 'credit bills' })).toHaveAttribute(
      'href',
      '/terminal',
    );
    expect(
      screen.getByRole('link', { name: /Card, DTP Card, Phone Pay and PTM totals/ }),
    ).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: /Close\s*nozzle/ })).toBeDisabled(); // nothing typed yet
  });
});

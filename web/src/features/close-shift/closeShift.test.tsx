import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { json } from '@/test/mockApi';

const tally = (over: Record<string, unknown> = {}) => ({
  fuel_rs: '0.00',
  oil_rs: '0.00',
  total_sale: '0.00',
  lines: [],
  collected: '0.00',
  difference: '0.00',
  status: 'balanced',
  credit_count: 0,
  expenses_count: 0,
  pending_expenses: 0,
  ...over,
});
const desk = (over: Record<string, unknown> = {}) => ({
  shift_id: 's1',
  nozzles: [
    { nozzle_id: 'n1', code: 'N1', fuel: 'Petrol', tank: 'MS-22', opening: '1000.000', closed: false, closing: null, testing: '0.000' },
  ],
  modes: [
    { tender_id: 't-card', name: 'Card', label: 'CARD', amount: null },
    { tender_id: 't-pp', name: 'PhonePe', label: 'PHONE PAY', amount: null },
  ],
  cash: { advance: '0.00', final: '0.00', recorded: false },
  tally: tally(),
  default_testing: '5.000',
  ...over,
});
const SHIFTS = () => json(200, [{ id: 's1', shift_date: '2026-10-13', shift_label: 'Morning', status: 'open' }]);

beforeEach(() => session.set(null));
afterEach(() => vi.unstubAllGlobals());

describe('Close Shift', () => {
  it('fills in the opening reading and the usual 5 litres of testing, and sends only what was typed', async () => {
    const api = await openAs(['shift.view', 'shift.manage', 'reconciliation.manage'], '/close-shift', 'Close Shift', {
      'GET /api/shifts': SHIFTS,
      'GET /api/close-shift/s1': () => json(200, desk()),
      'POST /api/close-shift/s1/tally': () => json(200, desk({ tally: tally({ total_sale: '50000.00', collected: '49000.00', difference: '1000.00', status: 'short' }) })),
      'POST /api/close-shift/s1': () => json(200, desk()),
    });
    const table = await screen.findByRole('table', { name: 'Nozzle readings' });
    expect(within(table).getByText('1,000')).toBeInTheDocument(); // opening = last closing, not typed
    expect(within(table).getByLabelText('Testing for N1')).toHaveValue('5');
    await userEvent.type(within(table).getByLabelText('Closing for N1'), '1505');
    await userEvent.type(screen.getByLabelText('CARD'), '10000');
    await userEvent.type(screen.getByLabelText('Advance'), '20000');
    // the tally comes from the Main PC, half a second after the last key
    expect(await screen.findByText('Short ₹1,000.00')).toBeInTheDocument();
    expect(api.calls.some((c) => c.key === 'POST /api/close-shift/s1')).toBe(false); // nothing saved yet
    await userEvent.click(screen.getByRole('button', { name: /Close shift/ }));
    await waitFor(() => expect(api.calls.some((c) => c.key === 'POST /api/close-shift/s1')).toBe(true));
    expect(api.calls.find((c) => c.key === 'POST /api/close-shift/s1')!.body).toEqual({
      readings: [{ nozzle_id: 'n1', closing: '1505', testing: '5', opening: null }],
      modes: [{ tender_id: 't-card', amount: '10000' }],
      advance: '20000',
      final: null,
    });
  });

  it('shows balanced and excess in words and colour, and recorded cash is shown, not typed', async () => {
    await openAs(['shift.view', 'shift.manage', 'reconciliation.manage'], '/close-shift', 'Close Shift', {
      'GET /api/shifts': SHIFTS,
      'GET /api/close-shift/s1': () =>
        json(200, desk({ cash: { advance: '20000.00', final: '14000.00', recorded: true }, tally: tally({ status: 'excess', difference: '-250.00', total_sale: '50000.00', collected: '50250.00' }) })),
    });
    expect(await screen.findByText('Excess ₹250.00')).toBeInTheDocument();
    expect(screen.getByLabelText('Advance (recorded earlier)')).toBeDisabled();
    expect(screen.getByRole('button', { name: /Close shift/ })).toBeDisabled(); // nothing new typed
  });
});

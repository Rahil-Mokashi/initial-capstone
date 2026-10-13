import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { json } from '@/test/mockApi';

const digest = (over: Record<string, unknown> = {}) => ({
  day: '2026-10-13',
  shifts: [
    { shift_id: 's1', label: 'Morning', total_sale: '50000.00', collected: '49000.00', difference: '1000.00', status: 'short', entry_status: 'entered' },
    { shift_id: 's2', label: 'Evening', total_sale: '30000.00', collected: '30250.00', difference: '-250.00', status: 'excess', entry_status: 'verified' },
  ],
  total_sale: '80000.00',
  litres_sold: '800.000',
  credit_sales: '5000.00',
  credit_outstanding: '120000.00',
  checks_total: 20,
  checks_passed: 18,
  checks_to_look_at: [{ sentence: 'Day 13 Oct: 1 entry not yet verified', status: 'warn' }],
  waiting: { entered: 1, verified: 1 },
  pending_expenses: 2,
  reviewed: [],
  reviewed_by_me: false,
  ...over,
});

beforeEach(() => session.set(null));
afterEach(() => vi.unstubAllGlobals());

describe('Daily digest', () => {
  it('says how each shift went in words, and what is waiting', async () => {
    await openAs(['digest.view'], '/digest', 'Daily digest', { 'GET /api/digest': () => json(200, digest()) });
    const shifts = await screen.findByRole('region', { name: 'Shifts' });
    expect(within(shifts).getByText('Short ₹1,000.00')).toBeInTheDocument();
    expect(within(shifts).getByText('Excess ₹250.00')).toBeInTheDocument();
    expect(within(shifts).getByText('Entered')).toBeInTheDocument();
    const waiting = screen.getByRole('region', { name: 'Waiting' });
    expect(within(waiting).getByText('1 shift not yet verified')).toBeInTheDocument();
    expect(within(waiting).getByText('2 expenses not yet approved')).toBeInTheDocument();
    expect(screen.getByText('18 of 20 passed')).toBeInTheDocument();
    expect(screen.getByText('₹1,20,000.00')).toBeInTheDocument();
  });

  it('lets an owner mark the day reviewed, and shows who already did', async () => {
    let reviewed = false;
    const api = await openAs(['digest.view'], '/digest', 'Daily digest', {
      'GET /api/digest': () => json(200, digest()),
      'POST /api/digest/review': () => {
        reviewed = true;
        return json(200, digest({ reviewed_by_me: true, reviewed: [{ by: 'owner1', at: '2026-10-13T05:00:00Z' }] }));
      },
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Mark as reviewed' }));
    await waitFor(() => expect(reviewed).toBe(true));
    expect(api.calls.find((c) => c.key === 'POST /api/digest/review')!.body).toEqual({ day: '2026-10-13' });
  });

  it('does not offer the button again once this owner has marked it', async () => {
    await openAs(['digest.view'], '/digest', 'Daily digest', {
      'GET /api/digest': () => json(200, digest({ reviewed_by_me: true, reviewed: [{ by: 'owner1', at: '2026-10-13T05:00:00Z' }] })),
    });
    expect(await screen.findByText(/Reviewed by owner1 at/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Mark as reviewed' })).toBeNull();
  });
});

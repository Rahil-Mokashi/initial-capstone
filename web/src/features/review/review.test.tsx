import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { json } from '@/test/mockApi';

const entry = (status: string, over: Record<string, unknown> = {}) => ({
  shift_id: 's1',
  shift_date: '2026-10-13',
  shift_label: 'Morning',
  status,
  events: [{ action: 'entered', from_status: null, to_status: 'entered', by: 'dataentry1', at: '2026-10-13T04:00:00Z', reason: null }],
  ...over,
});

beforeEach(() => session.set(null));
afterEach(() => vi.unstubAllGlobals());

describe('Review', () => {
  it('offers the accountant only Verify on an entered shift, and sends it', async () => {
    const api = await openAs(['entry.view', 'entry.verify'], '/review', 'Review', {
      'GET /api/entries': () => json(200, [entry('entered')]),
      'POST /api/entries/s1/verify': () => json(200, entry('verified')),
    });
    const list = await screen.findByRole('list', { name: 'Shifts' });
    expect(within(list).getByText('Waiting for the accountant to verify')).toBeInTheDocument();
    expect(within(list).queryByRole('button', { name: /^Approve/ })).toBeNull();
    expect(within(list).queryByRole('button', { name: /^Reopen/ })).toBeNull();
    await userEvent.click(within(list).getByRole('button', { name: /^Verify/ }));
    await waitFor(() => expect(api.calls.some((c) => c.key === 'POST /api/entries/s1/verify')).toBe(true));
  });

  it('offers an owner the next step and a reopen that needs a reason', async () => {
    const api = await openAs(['entry.view', 'entry.approve', 'entry.lock', 'entry.reopen'], '/review', 'Review', {
      'GET /api/entries': () => json(200, [entry('approved')]),
      'POST /api/entries/s1/lock': () => json(200, entry('locked')),
      'POST /api/entries/s1/reopen': () => json(200, entry('entered')),
    });
    await userEvent.click(await screen.findByRole('button', { name: /^Lock/ }));
    await waitFor(() => expect(api.calls.some((c) => c.key === 'POST /api/entries/s1/lock')).toBe(true));
    await userEvent.click(screen.getByRole('button', { name: /^Reopen/ }));
    await userEvent.type(await screen.findByLabelText(/What was wrong/), 'Card slip typed wrong');
    await userEvent.click(screen.getByRole('button', { name: 'Reopen' }));
    await waitFor(() => expect(api.calls.find((c) => c.key === 'POST /api/entries/s1/reopen')?.body).toEqual({ reason: 'Card slip typed wrong' }));
  });

  it('says what happened last, including a change after verifying', async () => {
    await openAs(['entry.view'], '/review', 'Review', {
      'GET /api/entries': () =>
        json(200, [entry('entered', { events: [{ action: 'data_changed', from_status: 'verified', to_status: 'entered', by: null, at: '2026-10-13T05:00:00Z', reason: 'Figures were changed after this was checked' }] })]),
    });
    expect(await screen.findByText(/Last: data changed at/)).toBeInTheDocument();
    expect(screen.getByText(/Figures were changed after this was checked/)).toBeInTheDocument();
  });

  it('a lock stopped by a failing check asks an owner for a reason, then locks anyway', async () => {
    let tries = 0;
    const api = await openAs(['entry.view', 'entry.lock'], '/review', 'Review', {
      'GET /api/entries': () => json(200, [entry('approved')]),
      'POST /api/entries/s1/lock': () =>
        ++tries === 1
          ? json(409, { error: { code: 'lock_blocked_by_checks', message: '1 check(s) are failing', details: { failing: ['Shift 1: cash does not add up'] } } })
          : json(200, entry('locked')),
    });
    await userEvent.click(await screen.findByRole('button', { name: /^Lock/ }));
    expect(await screen.findByText(/Shift 1: cash does not add up/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Why is it right to lock anyway/), 'explained to the owners');
    await userEvent.click(screen.getByRole('button', { name: 'Lock anyway' }));
    await waitFor(() => expect(api.calls.filter((c) => c.key === 'POST /api/entries/s1/lock').pop()?.body).toEqual({ override_reason: 'explained to the owners' }));
  });
});

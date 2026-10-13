import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { apiError, json } from '@/test/mockApi';
import { groupFingerprint } from './DevicesPage';

const device = (over: Record<string, unknown> = {}) => ({
  id: 'd1',
  name: 'Counter PC',
  enrolled_at: '2026-10-13T04:00:00Z',
  enrolled_ip: '192.168.1.21',
  last_seen_at: '2026-10-13T05:00:00Z',
  last_ip: '192.168.1.21',
  revoked_at: null,
  revoke_reason: null,
  ...over,
});

beforeEach(() => session.set(null));
afterEach(() => vi.unstubAllGlobals());

describe('devices', () => {
  it('groups a fingerprint so two screens can be compared by eye', () => {
    expect(groupFingerprint('abcd1234ef')).toBe('ABCD 1234 EF');
  });

  it('lists devices and shows the pairing code, the address and the fingerprint', async () => {
    const api = await openAs(['device.manage'], '/devices', 'Devices', {
      'GET /api/devices': () => json(200, [device(), device({ id: 'd2', name: 'Old PC', revoked_at: '2026-10-12T00:00:00Z' })]),
      'POST /api/devices/pairing': () =>
        json(200, {
          code: 'K7M2Q-9XA4B',
          minutes: 10,
          address: '192.168.1.10',
          port: 8443,
          pairing_port: 8444,
          ca_fingerprint: 'ab'.repeat(32),
        }),
    });
    const table = await screen.findByRole('table', { name: 'Devices' });
    expect(within(table).getByRole('cell', { name: 'Counter PC' })).toBeInTheDocument();
    expect(within(table).getByText('Active')).toBeInTheDocument();
    expect(within(table).getByText('Removed')).toBeInTheDocument();
    expect(within(table).queryByRole('button', { name: 'Remove Old PC' })).toBeNull(); // already removed
    await userEvent.click(screen.getByRole('button', { name: 'Add a device' }));
    expect(await screen.findByLabelText('Pairing code')).toHaveTextContent('K7M2Q-9XA4B');
    expect(screen.getByText('192.168.1.10, 8443, 8444')).toBeInTheDocument();
    expect(screen.getByLabelText('Fingerprint')).toHaveTextContent('AB'.repeat(2) + ' ' + 'AB'.repeat(2));
    // closing with Done must NOT cancel the code the other PC is about to use
    await userEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(api.calls.some((c) => c.key === 'POST /api/devices/pairing/cancel')).toBe(false);
  });

  it('cancels a code on request', async () => {
    const api = await openAs(['device.manage'], '/devices', 'Devices', {
      'GET /api/devices': () => json(200, []),
      'POST /api/devices/pairing': () =>
        json(200, { code: 'AAAAA-BBBBB', minutes: 10, address: '10.0.0.5', port: 8443, pairing_port: 8444, ca_fingerprint: 'cd'.repeat(32) }),
      'POST /api/devices/pairing/cancel': () => json(204, null),
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Add a device' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Cancel this code' }));
    await waitFor(() => expect(api.calls.some((c) => c.key === 'POST /api/devices/pairing/cancel')).toBe(true));
  });

  it('removes a device with a reason', async () => {
    const api = await openAs(['device.manage'], '/devices', 'Devices', {
      'GET /api/devices': () => json(200, [device()]),
      'POST /api/devices/d1/revoke': () => json(200, device({ revoked_at: '2026-10-13T06:00:00Z', revoke_reason: 'Stolen' })),
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Remove Counter PC' }));
    await userEvent.type(await screen.findByLabelText(/Reason for removing/), 'Stolen');
    await userEvent.click(screen.getByRole('button', { name: 'Remove' }));
    await waitFor(() => expect(api.calls.some((c) => c.key === 'POST /api/devices/d1/revoke')).toBe(true));
    expect(api.calls.find((c) => c.key === 'POST /api/devices/d1/revoke')!.body).toEqual({ reason: 'Stolen' });
  });

  it('says so plainly on a PC that works on its own', async () => {
    await openAs(['device.manage'], '/devices', 'Devices', {
      'GET /api/devices': () => apiError(404, 'not_found', 'This PC is not the Main PC.'),
    });
    expect(await screen.findByText(/This PC works on its own/)).toBeInTheDocument();
  });
});

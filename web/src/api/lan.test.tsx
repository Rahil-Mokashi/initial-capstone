import { act, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/api/client';
import { connection } from '@/api/connection';
import { takeEvents } from '@/api/live';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { apiError, json, mockApi } from '@/test/mockApi';

const ID = '3f2b7c1e-9d4a-4c11-8a55-0123456789ab';

function asClient() {
  (window as unknown as { pperp: unknown }).pperp = { mode: 'client', apiBase: '', launchSecret: 's', files: {}, print: {} };
  connection.reset();
}

beforeEach(() => {
  session.set(null);
  asClient();
});
afterEach(() => {
  delete (window as unknown as { pperp?: unknown }).pperp;
  connection.reset();
  vi.unstubAllGlobals();
});

describe('live stream parsing', () => {
  it('splits complete events and keeps the unfinished tail', () => {
    expect(takeEvents('data: {"type":"hello"}\n\ndata: {"type":"chan')).toEqual({ events: ['data: {"type":"hello"}'], rest: 'data: {"type":"chan' });
    expect(takeEvents(': beat\r\n\r\n')).toEqual({ events: [': beat'], rest: '' });
  });
});

describe('two people editing one record', () => {
  it('sends the version it read and shows who changed it first', async () => {
    const api_ = mockApi({
      [`GET /api/employees/${ID}`]: () => ({ status: 200, json: { id: ID }, headers: { ETag: '"4"' } }) as never,
      [`PATCH /api/employees/${ID}`]: () => apiError(409, 'conflict_stale', 'Changed by Asha at 14:05. Reload to see her change, then make yours again.', { changed_by: 'Asha', changed_at: '14:05' }),
    });
    // mockApi cannot set response headers on its own: wrap its fetch to add the ETag
    const inner = globalThis.fetch;
    vi.stubGlobal('fetch', async (...args: Parameters<typeof fetch>) => {
      const res = await inner(...args);
      if (String(args[0]).includes(`/api/employees/${ID}`) && (args[1]?.method ?? 'GET') === 'GET') return new Response(await res.text(), { status: res.status, headers: { 'Content-Type': 'application/json', ETag: '"4"' } });
      return res;
    });
    await api.get(`/employees/${ID}`);
    await expect(api.patch(`/employees/${ID}`, { first_name: 'X' })).rejects.toMatchObject({ code: 'conflict_stale', message: expect.stringContaining('Changed by Asha at 14:05') });
    expect(api_.calls.find((c) => c.key.startsWith('PATCH'))!.headers.get('If-Match')).toBe('"4"');
  });

  it('sends nothing extra for a record it never read', async () => {
    const other = '11111111-2222-4333-8444-555555555555';
    const api_ = mockApi({ [`PATCH /api/employees/${other}`]: () => json(200, {}) });
    await api.patch(`/employees/${other}`, { first_name: 'X' });
    expect(api_.calls[0]!.headers.get('If-Match')).toBeNull();
  });
});

describe('the Main PC cannot be reached', () => {
  it('refuses to save without even trying, but still lets screens read', async () => {
    const api_ = mockApi({ 'GET /api/tanks': () => json(200, []), 'POST /api/sales': () => json(201, {}) });
    connection.unreachable();
    await expect(api.post('/sales', {})).rejects.toMatchObject({ code: 'main_pc_unreachable' });
    expect(api_.calls.some((c) => c.key === 'POST /api/sales')).toBe(false);
    await api.get('/tanks');
    expect(connection.get().link).toBe('polling'); // an answer proves it is back
  });
});

describe('the connection light', () => {
  it('shows connected, then read-only when the Main PC goes away, in words', async () => {
    await openAs(['shift.view'], '/support', 'Support', {
      'GET /api/events': () => ({ status: 200 }),
    });
    expect(await screen.findByText(/Main PC (connected|connected \(refreshing every 20 s\))/)).toBeInTheDocument();
    act(() => connection.unreachable());
    expect(await screen.findByText(/Main PC not reachable - read only/)).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent(/nothing can be saved until it is back/);
    expect(screen.queryByText(/Offline — Local Only/)).toBeNull();
  });
});

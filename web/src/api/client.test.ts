import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiError, json, mockApi } from '@/test/mockApi';
import { api } from './client';
import { ApiError } from './errors';
import { session } from './session';

beforeEach(() => {
  session.set(null);
  window.pperp = undefined;
});
afterEach(() => {
  vi.unstubAllGlobals();
  session.onLost(null);
});

describe('api client', () => {
  it('sends the bearer token and the launch secret from the preload bridge', async () => {
    window.pperp = { apiBase: 'http://127.0.0.1:5555', launchSecret: 's3cret' } as never;
    session.set('tok');
    const { calls, fetchMock } = mockApi({ 'GET /api/tanks': () => json(200, []) });
    await api.get('/tanks');
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('http://127.0.0.1:5555/api/tanks');
    expect(calls[0]?.headers.get('Authorization')).toBe('Bearer tok');
    expect(calls[0]?.headers.get('X-Launch-Secret')).toBe('s3cret');
  });

  it('works same-origin without a bridge (the dev proxy adds the secret)', async () => {
    const { calls } = mockApi({ 'GET /api/tanks': () => json(200, []) });
    await api.get('/tanks');
    expect(calls[0]?.headers.get('X-Launch-Secret')).toBeNull();
  });

  it('turns an error envelope into ApiError', async () => {
    mockApi({
      'POST /api/tanks': () => apiError(409, 'conflict', 'A tank with code T1 already exists'),
    });
    await expect(api.post('/tanks', {})).rejects.toMatchObject({ status: 409, code: 'conflict' });
  });

  it('signs the app out when the session is lost, but not for a failed login', async () => {
    const lost = vi.fn();
    session.onLost(lost);
    mockApi({
      'GET /api/tanks': () => apiError(401, 'session_expired', 'ended'),
      'POST /api/auth/login': () => apiError(401, 'not_authenticated', 'nope'),
    });
    await expect(api.get('/tanks')).rejects.toBeInstanceOf(ApiError);
    expect(lost).toHaveBeenCalledTimes(1);
    await expect(api.post('/auth/login', {})).rejects.toBeInstanceOf(ApiError);
    expect(lost).toHaveBeenCalledTimes(1);
  });

  it('maps a dropped connection to network_error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    await expect(api.get('/tanks')).rejects.toMatchObject({ code: 'network_error', status: 0 });
  });

  it('returns undefined for 204', async () => {
    mockApi({ 'POST /api/auth/logout': () => ({ status: 204 }) });
    await expect(api.post('/auth/logout')).resolves.toBeUndefined();
  });
});

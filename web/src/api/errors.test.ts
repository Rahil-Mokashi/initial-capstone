import { describe, expect, it } from 'vitest';
import { ApiError, friendlyMessage, networkError, toApiError } from './errors';

const res = (status: number, body: unknown) =>
  new Response(typeof body === 'string' ? body : JSON.stringify(body), { status });

describe('toApiError', () => {
  it('reads the backend error envelope', async () => {
    const e = await toApiError(
      res(409, {
        error: {
          code: 'conflict',
          message: 'Receiving 9000 would exceed tank capacity',
          details: {},
        },
      }),
    );
    expect(e).toBeInstanceOf(ApiError);
    expect([e.status, e.code, e.message]).toEqual([
      409,
      'conflict',
      'Receiving 9000 would exceed tank capacity',
    ]);
  });

  it('keeps the permission name for 403', async () => {
    const e = await toApiError(
      res(403, {
        error: {
          code: 'permission_denied',
          message: 'x',
          details: { permission: 'inventory.manage' },
        },
      }),
    );
    expect(e.code).toBe('permission_denied');
    expect(e.details.permission).toBe('inventory.manage');
  });

  it('exposes per-field validation errors', async () => {
    const e = await toApiError(
      res(422, {
        error: {
          code: 'validation_error',
          message: 'bad',
          details: { fields: [{ field: 'capacity', message: 'must be positive' }] },
        },
      }),
    );
    expect(e.fieldErrors).toEqual([{ field: 'capacity', message: 'must be positive' }]);
  });

  it('maps an unknown code to "unknown" but keeps the message', async () => {
    const e = await toApiError(res(400, { error: { code: 'brand_new_code', message: 'Hello' } }));
    expect([e.code, e.message]).toEqual(['unknown', 'Hello']);
  });

  it('survives a non-JSON body (for example a proxy error page)', async () => {
    const e = await toApiError(res(502, '<html>Bad gateway</html>'));
    expect(e.code).toBe('unknown');
    expect(e.status).toBe(502);
    expect(e.message).toMatch(/unexpected error \(502\)/);
  });

  it('flags lost sessions', async () => {
    const expired = await toApiError(
      res(401, { error: { code: 'session_expired', message: 'x' } }),
    );
    const bad = await toApiError(
      res(401, { error: { code: 'invalid_credentials', message: 'x' } }),
    );
    expect(expired.isAuthLoss).toBe(true);
    expect(bad.isAuthLoss).toBe(false);
  });
});

describe('friendlyMessage', () => {
  it('explains permission errors in plain words', () => {
    const e = new ApiError(403, 'permission_denied', 'Permission denied: inventory.manage');
    expect(friendlyMessage(e)).toMatch(/don't have permission/i);
    expect(friendlyMessage(e)).not.toMatch(/inventory\.manage/);
  });

  it('joins field errors for validation failures', () => {
    const e = new ApiError(422, 'validation_error', 'bad', {
      fields: [
        { field: 'capacity', message: 'too big' },
        { field: '', message: 'nope' },
      ],
    });
    expect(friendlyMessage(e)).toBe('capacity: too big; nope');
  });

  it('has a safe fallback for non-API errors', () => {
    expect(friendlyMessage(new TypeError('boom internals'))).toBe(
      'Something went wrong. Please try again.',
    );
  });

  it('network errors say what to do', () => {
    const e = networkError();
    expect(e.code).toBe('network_error');
    expect(friendlyMessage(e)).toMatch(/reopen the app/i);
  });
});

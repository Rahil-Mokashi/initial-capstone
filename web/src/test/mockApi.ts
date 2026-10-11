import { vi } from 'vitest';

type Handler = (body: unknown, url: URL) => { status?: number; json?: unknown } | undefined;

export const json = (status: number, body: unknown) => ({ status, json: body });
export const apiError = (status: number, code: string, message: string, details: object = {}) =>
  json(status, { error: { code, message, details } });

/**
 * What the app shell asks for in the background on every screen (alert strip, shift indicator, search box,
 * device name). A test can still mock any of these itself; otherwise they answer "nothing to report".
 */
const SHELL_DEFAULTS: Record<string, Handler> = {
  'GET /api/alerts': () =>
    json(200, { total: 0, critical_count: 0, warning_count: 0, notifications: [] }),
  'GET /api/dashboard/summary': () => json(200, {}),
  'GET /api/system/device': () => json(200, { device: 'TEST-PC' }),
  'GET /api/employees': () => json(200, []),
  'GET /api/nozzles': () => json(200, []),
  'GET /api/tanks': () => json(200, []),
  'GET /api/users': () => json(200, []),
};

/** Replaces fetch with a router keyed by "METHOD /api/path". Unmatched calls fail loudly. */
export function mockApi(routes: Record<string, Handler>) {
  const calls: Array<{ key: string; body: unknown; headers: Headers; url: string }> = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://127.0.0.1');
    const key = `${init?.method ?? 'GET'} ${url.pathname}`;
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ key, body, headers: new Headers(init?.headers), url: String(input) });
    const handler = routes[key] ?? SHELL_DEFAULTS[key];
    if (!handler) throw new Error(`Unexpected request: ${key}`);
    const result = handler(body, url) ?? { status: 204 };
    return new Response(result.json === undefined ? null : JSON.stringify(result.json), {
      status: result.status ?? 200,
      headers: { 'Content-Type': 'application/json' },
    });
  });
  vi.stubGlobal('fetch', fetchMock);
  return { calls, fetchMock };
}

export const tank = (over: Record<string, unknown> = {}) => ({
  id: 't1',
  code: 'T1',
  fuel_id: 'f1',
  fuel_type: 'Petrol',
  status: 'active',
  capacity: '10000.000',
  current_stock: '2500.500',
  opening_stock: '2500.500',
  calibration_info: null,
  fill_percent: '25.01',
  is_low: false,
  ...over,
});

export const user = (permissions: string[], over: Record<string, unknown> = {}) => ({
  id: 'u1',
  username: 'manager1',
  first_name: 'Mona',
  last_name: 'Manager',
  role: 'MANAGER',
  permissions,
  must_change_password: false,
  has_pin: false,
  last_login: null,
  ...over,
});

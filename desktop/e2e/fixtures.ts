import {
  test as base,
  _electron as electron,
  expect,
  type ElectronApplication,
  type Page,
} from '@playwright/test';
import { copyFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { desktopDir, repoRoot, templateDb } from './global-setup';

export { expect };
export const PASSWORD = 'Passw0rd!x';

export interface Launched {
  app: ElectronApplication;
  page: Page;
  dbPath: string;
  userData: string;
  /** Every URL any page requested (even ones the blocker later cancelled). */
  requested: string[];
}

export async function launchApp(
  dir: string,
  opts: { userData?: string; dbPath?: string; env?: Record<string, string> } = {},
): Promise<Launched> {
  mkdirSync(dir, { recursive: true });
  const dbPath = opts.dbPath ?? join(dir, 'pump.db');
  if (!opts.dbPath) copyFileSync(templateDb, dbPath);
  const userData = opts.userData ?? join(dir, 'userData');

  const env: Record<string, string> = {};
  for (const [k, v] of Object.entries(process.env)) if (v !== undefined) env[k] = v;
  // This variable (set by some IDE terminals) makes Electron behave as plain Node.
  delete env.ELECTRON_RUN_AS_NODE;
  Object.assign(env, {
    PPERP_E2E: '1',
    PPERP_USER_DATA: userData,
    PETROL_PUMP_DB_PATH: dbPath,
    PPERP_WEB_DIR: join(repoRoot, 'web', 'dist'),
    PYTHONUTF8: '1',
    // What the file dialog returns in tests (a native dialog cannot be clicked in an automated run).
    PPERP_E2E_PICK_PATH: 'C:\\docs\\id-proof.pdf',
    ...opts.env,
  });

  const app = await electron.launch({ args: [desktopDir], cwd: desktopDir, env });
  const requested: string[] = [];
  app.context().on('request', (request) => requested.push(request.url()));
  const page = await app.firstWindow();
  return { app, page, dbPath, userData, requested };
}

/**
 * Signs in. By default the person was headed for Tanks (a deep link: sign-in returns you to where you were
 * going), which is where most specs start. Pass `home: true` to land on the Dashboard instead.
 */
export async function signIn(
  page: Page,
  username: string,
  password = PASSWORD,
  opts: { home?: boolean } = {},
): Promise<void> {
  if (!opts.home) await page.evaluate(() => (location.hash = '#/tanks'));
  await page.getByLabel('Username').fill(username);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: /^Sign in/i }).click();
}

export const test = base.extend<{ launched: Launched }>({
  // eslint-disable-next-line no-empty-pattern -- Playwright requires a destructuring pattern here
  launched: async ({}, use, testInfo) => {
    const launched = await launchApp(testInfo.outputPath('run'));
    await expect(launched.page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
    await use(launched);
    await launched.app.close().catch(() => undefined);
  },
});

type Json = Record<string, unknown>;

/**
 * Calls the app's own API from inside the running window (same origin, launch secret and a real
 * sign-in), for test SET-UP only: the thing under test is always driven through the UI.
 */
export async function apiAs(page: Page, username: string, password = PASSWORD) {
  const call = (method: string, path: string, body: unknown, token?: string) =>
    page.evaluate(
      async ([m, p, b, t]) => {
        const bridge = window.pperp!;
        const res = await fetch(`${bridge.apiBase}/api${p as string}`, {
          method: m as string,
          headers: {
            'Content-Type': 'application/json',
            'X-Launch-Secret': bridge.launchSecret,
            ...(t ? { Authorization: `Bearer ${t as string}` } : {}),
          },
          body: b === undefined ? undefined : JSON.stringify(b),
        });
        return { status: res.status, body: (await res.json().catch(() => null)) as unknown };
      },
      [method, path, body, token] as const,
    );
  const login = await call('POST', '/auth/login', { username, password });
  const token = (login.body as { token: string }).token;
  return async (method: string, path: string, body?: unknown): Promise<Json> => {
    const r = await call(method, path, body, token);
    if (r.status >= 400) throw new Error(`${method} ${path} -> ${r.status} ${JSON.stringify(r.body)}`);
    return r.body as Json;
  };
}

/** A priced Petrol fuel, nozzle N1 on tank T1, an open shift and an active assignment for EMP-0001. */
export async function setupPump(page: Page, price = '100.00') {
  const api = await apiAs(page, 'manager1');
  const fuels = (await api('GET', '/fuel-prices')) as unknown as Array<{ id: string; fuel_type: string }>;
  const petrol = fuels.find((f) => f.fuel_type === 'Petrol')!;
  await api('POST', `/fuel-prices/${petrol.id}/rate`, { new_rate_per_liter: price });
  const dispenser = (await api('POST', '/dispensers', { code: 'D1' })) as { id: string };
  const tanks = (await api('GET', '/tanks')) as unknown as Array<{ id: string; code: string }>;
  const nozzle = (await api('POST', '/nozzles', {
    code: 'N1',
    dispenser_id: dispenser.id,
    fuel_id: petrol.id,
    tank_id: tanks.find((t) => t.code === 'T1')!.id,
  })) as { id: string };
  const shift = (await api('POST', '/shifts', {
    shift_date: new Date().toISOString().slice(0, 10),
    shift_label: 'Morning',
  })) as { id: string };
  const employees = (await api('GET', '/employees')) as unknown as Array<{ id: string }>;
  await api('POST', `/shifts/${shift.id}/assignments`, {
    employee_id: employees[0]!.id,
    nozzle_id: nozzle.id,
    opening_meter: '0',
  });
  return { api, petrolId: petrol.id, nozzleId: nozzle.id, shiftId: shift.id, employeeId: employees[0]!.id };
}

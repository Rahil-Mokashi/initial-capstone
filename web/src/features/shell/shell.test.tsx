import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { greetingFor } from '@/features/dashboard/DashboardPage';
import { openAs } from '@/test/harness';
import { apiError, json } from '@/test/mockApi';

let alertSeq = 0;
const alert = (over: Record<string, unknown> = {}) => ({
  key: `k${++alertSeq}@2026-10-17`,
  count: 1,
  shortage: null,
  category: 'low_fuel',
  severity: 'critical',
  title: 'T2 is low on fuel',
  detail: 'It holds 9% of capacity.',
  action: 'Place a purchase order.',
  entity_id: 't2',
  is_summary: false,
  ...over,
});
const alerts = (items: ReturnType<typeof alert>[]) => ({
  total: items.length,
  critical_count: items.filter((a) => a.severity === 'critical').length,
  warning_count: items.filter((a) => a.severity === 'warning').length,
  notifications: items,
});
const tank = (over: Record<string, unknown> = {}) => ({
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
const ALL = [
  'sale.view',
  'shift.view',
  'inventory.view',
  'procurement.view',
  'employee.view',
  'nozzle.view',
  'user.manage',
];

beforeEach(() => {
  session.set(null);
  window.localStorage.clear();
});
afterEach(() => vi.unstubAllGlobals());

describe('dashboard', () => {
  it('greets by the time of day', () => {
    expect(greetingFor(8)).toBe('Good morning');
    expect(greetingFor(13)).toBe('Good afternoon');
    expect(greetingFor(20)).toBe('Good evening');
  });

  it('shows only the tiles the role may see, and warns when tanks run low', async () => {
    await openAs(ALL, '/', /Good (morning|afternoon|evening), Mona/, {
      'GET /api/dashboard/summary': () =>
        json(200, {
          sales_today_count: 12,
          sales_today_amount: '123456.50',
          open_shifts_count: 1,
          open_shift_labels: ['Morning'],
          low_stock_tanks_count: 2,
          pending_purchase_orders_count: 3,
        }),
      'GET /api/dashboard/sales-trend': () => json(200, []),
      'GET /api/dashboard/roster': () => json(200, []),
    });
    const tiles = await screen.findByRole('list', { name: 'Today at a glance' });
    expect(within(tiles).getByText('12')).toBeInTheDocument();
    expect(within(tiles).getByText('₹1,23,456.50')).toBeInTheDocument(); // Indian grouping
    expect(within(tiles).getByText('Tanks running low')).toBeInTheDocument();
    expect(within(tiles).getByText('Purchase orders pending')).toBeInTheDocument();
  });

  it('a role with no sales or shift rights sees none of those sections', async () => {
    await openAs(['inventory.view'], '/', /Good (morning|afternoon|evening), Mona/, {
      'GET /api/dashboard/summary': () => json(200, { low_stock_tanks_count: 0 }),
      'GET /api/tanks': () => json(200, [tank()]),
    });
    expect(await screen.findByText('Live tank levels')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Sales Trend' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /On Shift Now/ })).not.toBeInTheDocument();
  });

  it('shows the top three alerts and a link to all of them, or the all-clear line', async () => {
    const many = [
      alert({ title: 'A' }),
      alert({ title: 'B' }),
      alert({ title: 'C' }),
      alert({ title: 'D' }),
    ];
    await openAs(['inventory.view'], '/', /Good/, {
      'GET /api/alerts': () => json(200, alerts(many)),
    });
    const section = (await screen.findByRole('heading', { name: 'Attention needed' })).closest(
      'section',
    )!;
    expect(within(section).getAllByRole('listitem')).toHaveLength(3);
    expect(within(section).getByRole('link', { name: /View all 4 alerts/ })).toHaveAttribute(
      'href',
      '/alerts',
    );
  });

  it('the sales trend toggles between 7 and 30 days and prints exact amounts for each day', async () => {
    const api = await openAs(ALL, '/', /Good/, {
      'GET /api/dashboard/summary': () => json(200, {}),
      'GET /api/dashboard/roster': () => json(200, []),
      'GET /api/dashboard/sales-trend': (_b, url) => {
        const days = Number(url.searchParams.get('days'));
        return json(
          200,
          Array.from({ length: days }, (_, i) => ({
            day: `2026-10-${String(i + 1).padStart(2, '0')}`,
            amount: `${i + 1}00.00`,
          })),
        );
      },
    });
    const table = await screen.findByRole('table', { name: 'Daily sales revenue' });
    expect(within(table).getAllByRole('row')).toHaveLength(8); // header + 7
    await userEvent.click(screen.getByRole('button', { name: '30 Days' }));
    await waitFor(() =>
      expect(
        within(screen.getByRole('table', { name: 'Daily sales revenue' })).getAllByRole('row'),
      ).toHaveLength(31),
    );
    expect(api.calls.some((c) => c.key === 'GET /api/dashboard/sales-trend')).toBe(true);
  });

  it('shows who is on a nozzle now, capped at six with a +N more line', async () => {
    const rows = Array.from({ length: 8 }, (_, i) => ({
      name: `Person ${i}`,
      detail: 'N1 · Petrol · Morning · since 08:00',
    }));
    await openAs(ALL, '/', /Good/, {
      'GET /api/dashboard/summary': () => json(200, {}),
      'GET /api/dashboard/sales-trend': () => json(200, []),
      'GET /api/dashboard/roster': () => json(200, rows),
    });
    expect(await screen.findByRole('heading', { name: 'On Shift Now (8)' })).toBeInTheDocument();
    expect(screen.getByText('+2 more on shift')).toBeInTheDocument();
    expect(screen.queryByText('Person 7')).not.toBeInTheDocument();
  });

  it('the figures failing to load never blocks the rest, and says so', async () => {
    await openAs(['inventory.view'], '/', /Good/, {
      'GET /api/dashboard/summary': () => apiError(500, 'internal_error', 'boom'),
      'GET /api/tanks': () => json(200, [tank()]),
    });
    expect(await screen.findByText(/Today.s figures could not be loaded/)).toBeInTheDocument();
    expect(await screen.findByText('Live tank levels')).toBeInTheDocument();
  });
});

describe('alerts', () => {
  it('the Alerts page lists every alert with its severity in words, or an empty explanation', async () => {
    await openAs(['inventory.view'], '/alerts', 'Alerts', {
      'GET /api/alerts': () =>
        json(200, alerts([alert(), alert({ severity: 'warning', title: 'Warn one' })])),
    });
    expect(await screen.findByText('NEEDS ATTENTION')).toBeInTheDocument();
    expect(screen.getByText('WORTH A LOOK')).toBeInTheDocument();
    expect(
      screen.getByText(/2 alert\(s\): 1 needing attention, 1 worth a look/),
    ).toBeInTheDocument();
  });

  it('says plainly when the list cannot be loaded, instead of looking like all clear', async () => {
    await openAs(['inventory.view'], '/alerts', 'Alerts', {
      'GET /api/alerts': () => apiError(500, 'internal_error', 'boom'),
    });
    expect(await screen.findByText('Could not load this')).toBeInTheDocument();
  });

  it('the strip quotes a single alert in full, or counts and names the most urgent', async () => {
    await openAs(['inventory.view'], '/', /Good/, {
      'GET /api/alerts': () => json(200, alerts([alert()])),
    });
    expect(await screen.findByRole('status', { name: '' })).toBeTruthy();
    expect(
      await screen.findByText(
        'T2 is low on fuel. It holds 9% of capacity. Place a purchase order.',
        { selector: 'p[role="status"]' },
      ),
    ).toBeInTheDocument();
  });

  it('the strip expands to every alert and clicking one opens the screen it is about', async () => {
    await openAs(ALL, '/', /Good/, {
      'GET /api/alerts': () =>
        json(
          200,
          alerts([
            alert({ title: 'Tank low' }),
            alert({
              category: 'outstanding_credit',
              title: 'ACME owes money',
              severity: 'warning',
            }),
          ]),
        ),
      'GET /api/credit/accounts': () => json(200, []),
      'GET /api/dashboard/summary': () => json(200, {}),
      'GET /api/dashboard/sales-trend': () => json(200, []),
      'GET /api/dashboard/roster': () => json(200, []),
    });
    expect(
      await screen.findByText(/2 alerts need attention — most urgent: Tank low\./),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Show all 2/ }));
    await userEvent.click(screen.getByRole('button', { name: /ACME owes money/ }));
    expect(await screen.findByRole('heading', { name: 'Credit Management' })).toBeInTheDocument();
  });

  it('the top-bar Alerts button carries the count and previews three alerts', async () => {
    await openAs(['inventory.view'], '/support', 'Support', {
      'GET /api/alerts': () =>
        json(
          200,
          alerts([
            alert({ title: 'One' }),
            alert({ title: 'Two' }),
            alert({ title: 'Three' }),
            alert({ title: 'Four' }),
          ]),
        ),
    });
    const button = await screen.findByRole('button', { name: 'Alerts (4)' });
    await userEvent.click(button);
    const panel = screen.getByRole('region', { name: 'Alerts (4)' });
    expect(within(panel).getAllByRole('listitem')).toHaveLength(3);
    await userEvent.click(within(panel).getByRole('button', { name: /View all 4 alerts/ }));
    expect(await screen.findByRole('heading', { name: 'Alerts', level: 1 })).toBeInTheDocument();
  });
});

describe('account menu, lock screen, PIN and password', () => {
  const open = (over: Record<string, unknown> = {}, routes = {}) =>
    openAs(['inventory.view'], '/support', 'Support', routes, over);

  it('shows who is signed in, their role and the previous sign-in', async () => {
    await open({ last_login: '2026-10-10T09:15:00Z' });
    await userEvent.click(screen.getByRole('button', { name: /Account menu/ }));
    const panel = screen.getByRole('region', { name: /Account menu/ });
    expect(within(panel).getByText('Mona Manager')).toBeInTheDocument();
    expect(within(panel).getByText('MANAGER')).toBeInTheDocument();
    expect(within(panel).getByText(/Last sign-in: /)).toBeInTheDocument();
  });

  it('locks the app behind a re-check of the password, and the same session resumes', async () => {
    let n = 0;
    const api = await open(
      {},
      {
        'POST /api/auth/reauthenticate': () =>
          n++ === 0
            ? apiError(401, 'invalid_credentials', "That's not correct. Please try again.")
            : { status: 204 },
      },
    );
    await userEvent.click(screen.getByRole('button', { name: /Account menu/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Lock' }));
    const lock = await screen.findByRole('dialog', { name: /Welcome back, Mona/ });
    expect(document.querySelector('[inert]')).not.toBeNull(); // everything behind the overlay is unreachable
    await userEvent.click(within(lock).getByRole('button', { name: 'Unlock' }));
    expect(await within(lock).findByRole('alert')).toHaveTextContent('Please enter your password.');
    await userEvent.type(within(lock).getByLabelText('Password'), 'wrong');
    await userEvent.click(within(lock).getByRole('button', { name: 'Unlock' }));
    expect(await within(lock).findByRole('alert')).toHaveTextContent("That's not correct");
    expect(within(lock).getByLabelText('Password')).toHaveValue(''); // cleared after a failure
    await userEvent.type(within(lock).getByLabelText('Password'), 'Passw0rd!x');
    await userEvent.click(within(lock).getByRole('button', { name: 'Unlock' }));
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: /Welcome back/ })).not.toBeInTheDocument(),
    );
    expect(api.calls.filter((c) => c.key === 'POST /api/auth/reauthenticate').pop()?.body).toEqual({
      credential: 'Passw0rd!x',
      use_pin: false,
    });
    expect(api.calls.filter((c) => c.key === 'POST /api/auth/login')).toHaveLength(1); // no new sign-in
  });

  it('offers the PIN on the lock screen only to someone who has one, and Escape does not dismiss it', async () => {
    await open({ has_pin: true }, { 'POST /api/auth/reauthenticate': () => ({ status: 204 }) });
    await userEvent.click(screen.getByRole('button', { name: /Account menu/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Lock' }));
    const lock = await screen.findByRole('dialog', { name: /Welcome back/ });
    await userEvent.keyboard('{Escape}');
    expect(screen.getByRole('dialog', { name: /Welcome back/ })).toBeInTheDocument();
    await userEvent.click(within(lock).getByRole('button', { name: 'Use PIN instead' }));
    await userEvent.type(within(lock).getByLabelText('PIN'), '483920');
    await userEvent.click(within(lock).getByRole('button', { name: 'Unlock' }));
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: /Welcome back/ })).not.toBeInTheDocument(),
    );
  });

  it('"Sign out instead" on the lock screen ends the session', async () => {
    const api = await open();
    await userEvent.click(screen.getByRole('button', { name: /Account menu/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Lock' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Sign out instead' }));
    expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
    expect(api.calls.some((c) => c.key === 'POST /api/auth/logout')).toBe(true);
  });

  it('sets a PIN after checking it is six digits and matches, then refreshes the account', async () => {
    const api = await open(
      {},
      {
        'POST /api/auth/pin': () => json(200, { id: 'u1' }),
        'GET /api/auth/me': () =>
          json(200, {
            ...{
              id: 'u1',
              username: 'manager1',
              first_name: 'Mona',
              last_name: 'Manager',
              role: 'MANAGER',
              permissions: ['inventory.view'],
              must_change_password: false,
            },
            has_pin: true,
            last_login: null,
          }),
      },
    );
    await userEvent.click(screen.getByRole('button', { name: /Account menu/ }));
    expect(screen.getByRole('button', { name: 'Set a quick sign-in PIN' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Set a quick sign-in PIN' }));
    const d = screen.getByRole('dialog');
    await userEvent.type(within(d).getByLabelText('Current password'), 'Passw0rd!x');
    await userEvent.type(within(d).getByLabelText('New PIN'), '123');
    await userEvent.type(within(d).getByLabelText('Confirm PIN'), '123');
    await userEvent.click(within(d).getByRole('button', { name: 'Set PIN' }));
    expect(await within(d).findByText('The PIN must be exactly 6 digits.')).toBeInTheDocument();
    await userEvent.clear(within(d).getByLabelText('New PIN'));
    await userEvent.type(within(d).getByLabelText('New PIN'), '483920');
    await userEvent.clear(within(d).getByLabelText('Confirm PIN'));
    await userEvent.type(within(d).getByLabelText('Confirm PIN'), '483921');
    await userEvent.click(within(d).getByRole('button', { name: 'Set PIN' }));
    expect(
      await within(d).findByText('New PIN and confirmation do not match.'),
    ).toBeInTheDocument();
    await userEvent.clear(within(d).getByLabelText('Confirm PIN'));
    await userEvent.type(within(d).getByLabelText('Confirm PIN'), '483920');
    await userEvent.click(within(d).getByRole('button', { name: 'Set PIN' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.calls.find((c) => c.key === 'POST /api/auth/pin')?.body).toEqual({
      current_password: 'Passw0rd!x',
      pin: '483920',
    });
    await userEvent.click(screen.getByRole('button', { name: /Account menu/ }));
    expect(
      await screen.findByRole('button', { name: 'Change quick sign-in PIN' }),
    ).toBeInTheDocument();
  });

  it('changes the password voluntarily and shows a weak-password refusal inside the dialog', async () => {
    let n = 0;
    const api = await open(
      {},
      {
        'POST /api/auth/change-password': () =>
          n++ === 0
            ? apiError(422, 'weak_password', 'Password is too weak.')
            : json(200, { id: 'u1' }),
      },
    );
    await userEvent.click(screen.getByRole('button', { name: /Account menu/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Change password' }));
    const d = screen.getByRole('dialog');
    await userEvent.type(within(d).getByLabelText('Current password'), 'Passw0rd!x');
    await userEvent.type(within(d).getByLabelText('New password'), 'weak');
    await userEvent.type(within(d).getByLabelText('New password again'), 'weak');
    await userEvent.click(within(d).getByRole('button', { name: 'Save new password' }));
    expect(await within(d).findByRole('alert')).toHaveTextContent('too weak');
    await userEvent.clear(within(d).getByLabelText('New password'));
    await userEvent.type(within(d).getByLabelText('New password'), 'Str0ng!Passw0rd');
    await userEvent.clear(within(d).getByLabelText('New password again'));
    await userEvent.type(within(d).getByLabelText('New password again'), 'Str0ng!Passw0rd');
    await userEvent.click(within(d).getByRole('button', { name: 'Save new password' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.calls.filter((c) => c.key === 'POST /api/auth/change-password').pop()?.body).toEqual(
      {
        current_password: 'Passw0rd!x',
        new_password: 'Str0ng!Passw0rd',
      },
    );
  });

  it('dark mode is switched from the account menu and remembered', async () => {
    await open();
    await userEvent.click(screen.getByRole('button', { name: /Account menu/ }));
    const toggle = screen.getByRole('button', { name: /Dark mode/ });
    await userEvent.click(toggle);
    expect(document.documentElement.getAttribute('data-theme')).toMatch(/dark|light/);
    expect(window.localStorage.getItem('pperp.theme')).toBe(
      document.documentElement.getAttribute('data-theme'),
    );
  });
});

describe('top bar', () => {
  it('shows whether a shift is open (and no offline chip)', async () => {
    await openAs(['shift.view'], '/support', 'Support', {
      'GET /api/dashboard/summary': () =>
        json(200, { open_shifts_count: 1, open_shift_labels: ['Morning'] }),
    });
    expect(screen.queryByText(/Offline — Local Only/)).toBeNull();
    expect(await screen.findByText('Shift: Morning • Open')).toBeInTheDocument();
  });

  it('the shift indicator disappears for a role that cannot see shifts', async () => {
    await openAs(['inventory.view'], '/support', 'Support', {
      'GET /api/dashboard/summary': () => json(200, { low_stock_tanks_count: 0 }),
    });
    expect(screen.queryByText(/No shift open|Shift:/)).not.toBeInTheDocument();
  });

  const RECORDS = [
    { kind: 'Employee', label: 'Ravi Kumar', hint: 'EMP-0001', to: '/employees' },
    { kind: 'Nozzle', label: 'Nozzle N7', hint: 'D1', to: '/nozzles' },
    { kind: 'Tank', label: 'Tank T9', hint: 'Petrol', to: '/tanks/t9' },
    { kind: 'User', label: 'night.manager', hint: 'Night Manager', to: '/users/u9' },
    { kind: 'Vehicle', label: 'MH12AB1234', hint: 'Ravi Transport', to: '/credit/customers/c1' },
  ];
  const box = () => screen.getByRole('combobox', { name: /Search screens/ });

  it('finds records and opens the screen they are on', async () => {
    await openAs(ALL, '/support', 'Support', { 'GET /api/search/records': () => json(200, RECORDS) });
    await userEvent.type(box(), 'ravi kumar');
    await userEvent.click(await screen.findByRole('option', { name: /Ravi Kumar/ }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Employees' })).toBeInTheDocument();
  });

  it('forgives typos and knows pump words', async () => {
    await openAs(ALL, '/support', 'Support', { 'GET /api/search/records': () => json(200, RECORDS) });
    await userEvent.type(box(), 'nozel');
    expect(await screen.findByRole('option', { name: /Nozzle N7/ })).toBeInTheDocument();
    await userEvent.clear(box());
    await userEvent.type(box(), 'petrol');
    expect(await screen.findByRole('option', { name: /Tank T9/ })).toBeInTheDocument();
    await userEvent.clear(box());
    await userEvent.type(box(), 'mh12ab');
    expect(await screen.findByRole('option', { name: /MH12AB1234/ })).toBeInTheDocument();
    await userEvent.clear(box());
    await userEvent.type(box(), 'zzzz');
    expect(screen.queryByRole('option')).not.toBeInTheDocument();
    expect(screen.getByText(/Nothing found/)).toBeInTheDocument();
  });

  it('finds screens and actions, and only those this role can open', async () => {
    await openAs(['inventory.view', 'inventory.manage'], '/support', 'Support', {
      'GET /api/search/records': () => json(200, []),
    });
    await userEvent.type(box(), 'record dip');
    expect(await screen.findByRole('option', { name: /Record a dip reading/ })).toBeInTheDocument();
    await userEvent.clear(box());
    await userEvent.type(box(), 'payroll');
    expect(screen.queryByRole('option', { name: /Payroll/ })).not.toBeInTheDocument();
    await userEvent.clear(box());
    await userEvent.type(box(), 'add employee');
    expect(screen.queryByRole('option', { name: /Add an employee/ })).not.toBeInTheDocument();
  });

  it('opens with Ctrl+K, moves with the arrow keys, goes with Enter, and offers the last searches', async () => {
    await openAs(ALL, '/support', 'Support', { 'GET /api/search/records': () => json(200, RECORDS) });
    await userEvent.keyboard('{Control>}k{/Control}');
    expect(box()).toHaveFocus();
    await userEvent.type(box(), 'employees');
    await userEvent.keyboard('{Enter}');
    expect(await screen.findByRole('heading', { level: 1, name: 'Employees' })).toBeInTheDocument();
    await userEvent.click(box());
    const recent = await screen.findByRole('listbox', { name: 'Recent searches' });
    expect(within(recent).getByText('employees')).toBeInTheDocument();
  });
});

describe('support', () => {
  it('is reachable from the sidebar by everyone and explains the offline model', async () => {
    await openAs(['inventory.view'], '/', /Good/, { 'GET /api/tanks': () => json(200, []) });
    await userEvent.click(screen.getByRole('link', { name: 'Support' }));
    expect(await screen.findByRole('heading', { name: 'Support', level: 1 })).toBeInTheDocument();
    expect(screen.getByText(/This app works fully offline/)).toBeInTheDocument();
    expect(screen.getByText('Account or access problem')).toBeInTheDocument();
    expect(screen.getByText('Lost or corrupted data')).toBeInTheDocument();
  });
});

describe('checks updating chip', () => {
  it('shows while the Main PC is still running checks, then goes away', async () => {
    let updating = true;
    await openAs(['shift.view'], '/support', 'Support', {
      'GET /api/checks/status': () => json(200, { updating }),
    });
    expect(await screen.findByText(/Checks updating/)).toBeInTheDocument();
    updating = false;
    await waitFor(() => expect(screen.queryByText(/Checks updating/)).toBeNull(), { timeout: 5000 });
  });
});

describe('alert actions', () => {
  const short = alert({
    category: 'cash_shortage',
    title: 'Cash short by 114.49',
    shortage: {
      line_id: 'ln1',
      shift: '2026-10-17 Morning',
      employees: [
        { id: 'e1', name: 'Asha Patil' },
        { id: 'e2', name: 'Ravi Shinde' },
      ],
      suggested_employee_id: null,
    },
  });

  it('marks a cash shortage against the chosen person of that shift', async () => {
    const api = await openAs(['inventory.view', 'shortage.manage'], '/alerts', 'Alerts', {
      'GET /api/alerts': () => json(200, alerts([short])),
      'POST /api/alerts/shortage': () => new Response(null, { status: 204 }),
    });
    await userEvent.selectOptions(await screen.findByLabelText('Who handed in the cash'), 'e2');
    await userEvent.click(screen.getByRole('button', { name: 'Mark against Ravi Shinde' }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/alerts/shortage')?.body).toEqual({ line_id: 'ln1', employee_id: 'e2' }),
    );
  });

  it('acknowledges with a reason, and shows a count when the same alert repeats', async () => {
    const api = await openAs(['inventory.view', 'alert.acknowledge'], '/alerts', 'Alerts', {
      'GET /api/alerts': () => json(200, alerts([alert({ count: 3, key: 'abc@2026-10-17' })])),
      'POST /api/alerts/acknowledge': () => new Response(null, { status: 204 }),
    });
    expect(await screen.findByText('× 3')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /^Acknowledge/ }));
    await userEvent.type(await screen.findByLabelText(/Why can it be set aside/), 'known, being fixed');
    await userEvent.click(screen.getByRole('button', { name: 'Acknowledge' }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/alerts/acknowledge')?.body).toEqual({ key: 'abc@2026-10-17', reason: 'known, being fixed' }),
    );
  });

  it('shows no Mark or Acknowledge buttons to someone without the permission', async () => {
    await openAs(['inventory.view'], '/alerts', 'Alerts', { 'GET /api/alerts': () => json(200, alerts([short])) });
    await screen.findByText('Cash short by 114.49');
    expect(screen.queryByRole('button', { name: /^Mark against/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Acknowledge/ })).toBeNull();
  });
});

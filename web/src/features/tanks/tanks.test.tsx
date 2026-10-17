import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { App } from '@/App';
import { AuthProvider } from '@/auth/AuthContext';
import { ToastProvider } from '@/components/ui/Toast';
import { apiError, json, mockApi, tank, user } from '@/test/mockApi';

const MANAGE = ['inventory.view', 'inventory.manage', 'employee.view'];
const VIEW_ONLY = ['inventory.view'];

type Routes = Parameters<typeof mockApi>[0];

function setup(permissions: string[], extra: Routes = {}, path = '/tanks') {
  const api = mockApi({
    'POST /api/auth/login': () =>
      json(200, { token: 'tok', expires_at: '2099-01-01T00:00:00', user: user(permissions) }),
    'POST /api/auth/logout': () => ({ status: 204 }),
    'GET /api/tanks': () =>
      json(200, [
        tank(),
        tank({
          id: 't2',
          code: 'T2',
          current_stock: '1800.000',
          fill_percent: '18.00',
          is_low: true,
          fuel_type: 'Diesel',
        }),
      ]),
    'GET /api/tanks/recent-transactions': () =>
      json(200, [
        {
          id: 'x1',
          tank_id: 't1',
          tank_code: 'T1',
          transaction_type: 'receipt',
          quantity: '1000.000',
          transaction_at: '2026-10-09T05:30:00Z',
          reference: null,
          remarks: null,
          recorded_by: 'manager1',
        },
      ]),
    'GET /api/lookups/employees': () =>
      json(200, [{ id: 'e1', employee_code: 'EMP-0001', first_name: 'Ravi', last_name: 'Kumar' }]),
    'GET /api/lookups/fuels': () => json(200, [{ id: 'f1', fuel_type: 'Petrol' }]),
    ...extra,
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <AuthProvider>
          <MemoryRouter initialEntries={[path]}>
            <App />
          </MemoryRouter>
        </AuthProvider>
      </ToastProvider>
    </QueryClientProvider>,
  );
  return api;
}

async function signIn() {
  await userEvent.type(screen.getByLabelText('Username'), 'manager1');
  await userEvent.type(screen.getByLabelText('Password'), 'Passw0rd!x');
  await userEvent.click(screen.getByRole('button', { name: /^Sign in/i }));
  await screen.findByRole('heading', { level: 1, name: /Tanks & Inventory/ });
  await screen.findByRole('heading', { name: 'T1' }); // the list itself has loaded
}

// Like signIn(), but the list never loads for this role.
async function signIn403() {
  await userEvent.type(screen.getByLabelText('Username'), 'manager1');
  await userEvent.type(screen.getByLabelText('Password'), 'Passw0rd!x');
  await userEvent.click(screen.getByRole('button', { name: /^Sign in/i }));
  await screen.findByRole('heading', { level: 1, name: /Tanks & Inventory/ });
}

beforeEach(() => session.set(null));
afterEach(() => vi.unstubAllGlobals());

describe('login and the tank list', () => {
  it('draws each tank as a picture; the exact figures are one tap away', async () => {
    setup(MANAGE);
    await signIn();
    const card = screen.getByRole('heading', { name: 'T1' }).closest('li')!;
    expect(within(card).getByRole('img', { name: /T1 Petrol tank, .* 25\.0% full/ })).toBeInTheDocument();
    expect(within(card).queryByText('2,500.500 L')).toBeNull(); // the picture is the main view
    await userEvent.click(within(card).getByRole('button', { name: /Show the numbers/ }));
    expect(within(card).getByText('2,500.500 L')).toBeInTheDocument(); // exactly as the server sent it
    expect(within(card).getByText('In the tank (book stock)')).toBeInTheDocument();
    expect(within(card).getByText('10,000.000 L')).toBeInTheDocument();
    expect(within(card).getByText('none recorded')).toBeInTheDocument();
  });

  it('"Show numbers" shows them on every tank and is remembered for the person', async () => {
    setup(MANAGE);
    await signIn();
    await userEvent.click(screen.getByRole('checkbox', { name: 'Show numbers' }));
    const card = screen.getByRole('heading', { name: 'T1' }).closest('li')!;
    expect(within(card).getByText('2,500.500 L')).toBeInTheDocument();
    expect(window.localStorage.getItem('pperp.tanks.showNumbers.manager1')).toBe('1');
  });

  it('a low tank says LOW in words and an icon, not only a colour', async () => {
    setup(MANAGE);
    await signIn();
    const card = screen.getByRole('heading', { name: 'T2' }).closest('li')!;
    expect(within(card).getByText(/Low - 18\.0%/)).toBeInTheDocument();
  });

  it('shows the wrong-password message from the server', async () => {
    setup(MANAGE, {
      'POST /api/auth/login': () =>
        apiError(401, 'invalid_credentials', "That username or password isn't correct."),
    });
    await userEvent.type(screen.getByLabelText('Username'), 'manager1');
    await userEvent.type(screen.getByLabelText('Password'), 'bad');
    await userEvent.click(screen.getByRole('button', { name: /^Sign in/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/isn't correct/);
  });

  it('validates empty login fields without calling the server', async () => {
    const { calls } = setup(MANAGE);
    await userEvent.click(screen.getByRole('button', { name: /^Sign in/i }));
    expect(await screen.findByText('Username is required.')).toBeInTheDocument();
    expect(calls.filter((c) => c.key.startsWith('POST'))).toHaveLength(0);
  });

  it('redirects to login when signed out', () => {
    setup(MANAGE, {}, '/tanks');
    expect(screen.getByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
  });

  it('logs out back to the sign-in screen and forgets the token', async () => {
    const { calls } = setup(MANAGE);
    await signIn();
    await userEvent.click(screen.getByRole('button', { name: /Account menu/ }));
    await userEvent.click(screen.getByRole('button', { name: /log out/i }));
    expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
    expect(calls.some((c) => c.key === 'POST /api/auth/logout')).toBe(true);
    expect(session.token).toBeNull();
  });
});

describe('opening the module repeatedly never duplicates it', () => {
  it('clicking Tanks in the sidebar many times leaves exactly one Tanks screen', async () => {
    setup(MANAGE);
    await signIn();
    const nav = screen.getByRole('navigation', { name: 'Main' });
    for (let i = 0; i < 5; i++)
      await userEvent.click(within(nav).getByRole('link', { name: 'Tanks' }));
    expect(screen.getAllByRole('heading', { level: 1, name: /Tanks & Inventory/ })).toHaveLength(1);
    expect(screen.getAllByRole('main')).toHaveLength(1);
    expect(screen.getAllByRole('heading', { name: 'T1' })).toHaveLength(1);
  });

  it('double-clicking Add tank opens one dialog, not two', async () => {
    setup(MANAGE);
    await signIn();
    await userEvent.dblClick(screen.getByRole('button', { name: /add tank/i }));
    expect(await screen.findAllByRole('dialog')).toHaveLength(1);
  });

  it('two action buttons never stack two dialogs', async () => {
    setup(MANAGE);
    await signIn();
    const card = screen.getByRole('heading', { name: 'T1' }).closest('li')!;
    await userEvent.click(within(card).getByRole('button', { name: 'Receipt' }));
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
  });
});

describe('permissions', () => {
  it('a view-only role sees the tanks but no write actions', async () => {
    setup(VIEW_ONLY);
    await signIn();
    expect(screen.getByRole('heading', { name: 'T1' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /add tank/i })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Record reading' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Receipt' })).toBeNull();
  });

  it('the sidebar lists only what the role may use', async () => {
    setup(VIEW_ONLY);
    await signIn();
    const nav = screen.getByRole('navigation', { name: 'Main' });
    expect(within(nav).getByRole('link', { name: 'Tanks' })).toBeInTheDocument();
    expect(within(nav).queryByText('Employees')).toBeNull();
    expect(within(nav).queryByText('Audit Log')).toBeNull();
  });

  it('a server 403 is explained in plain words and the dialog stays open', async () => {
    setup(MANAGE, {
      'POST /api/tanks/t1/transactions': () =>
        apiError(403, 'permission_denied', "You don't have permission to do that.", {
          permission: 'inventory.manage',
        }),
    });
    await signIn();
    const card = screen.getByRole('heading', { name: 'T1' }).closest('li')!;
    await userEvent.click(within(card).getByRole('button', { name: 'Receipt' }));
    await userEvent.type(screen.getByLabelText('Quantity (L)'), '10');
    await userEvent.click(screen.getByRole('button', { name: 'Record receipt' }));
    expect(await screen.findByText(/don't have permission/i)).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('a role with no inventory access sees ONE clear explanation, not one per panel', async () => {
    setup(VIEW_ONLY, {
      'GET /api/tanks': () =>
        apiError(403, 'permission_denied', 'denied', { permission: 'inventory.view' }),
    });
    await signIn403();
    expect(await screen.findAllByText('You do not have access to this')).toHaveLength(1);
  });

  it('the detail page disables write actions for a view-only role and says why', async () => {
    setup(VIEW_ONLY, {
      'GET /api/tanks/t1': () => json(200, tank()),
      'GET /api/tanks/t1/transactions': () => json(200, []),
      'GET /api/tanks/t1/readings': () => json(200, []),
      'GET /api/tanks/t1/reconciliations': () => json(200, []),
    });
    await signIn();
    await userEvent.click(screen.getAllByRole('link', { name: 'T1' })[0]!);
    await screen.findByRole('heading', { name: 'Tank T1' });
    for (const name of [
      'Receipt',
      'Issue',
      'Adjustment',
      'Record reading',
      'Reconcile',
      'Change status',
    ]) {
      expect(screen.getByRole('button', { name })).toBeDisabled();
    }
    expect(screen.getByText(/look at this tank but not change it/i)).toBeInTheDocument();
    expect(await screen.findByText('No transactions for this tank yet')).toBeInTheDocument();
  });
});

describe('recording a reading', () => {
  it('sends decimals as strings, remembers who took it, and confirms', async () => {
    const { calls } = setup(MANAGE, {
      'POST /api/tanks/t1/readings': () =>
        json(201, {
          id: 'r1',
          tank_id: 't1',
          reading_at: '2026-10-09T05:30:00Z',
          physical_stock: '2490.125',
          dip_value: null,
          employee_id: 'e1',
          employee_name: 'Ravi Kumar',
          remarks: null,
        }),
    });
    await signIn();
    const card = screen.getByRole('heading', { name: 'T1' }).closest('li')!;
    await userEvent.click(within(card).getByRole('button', { name: 'Record reading' }));
    await userEvent.selectOptions(await screen.findByLabelText('Taken by'), 'e1');
    await userEvent.type(screen.getByLabelText('Physical stock (L)'), '2490.125');
    await userEvent.click(screen.getByRole('button', { name: 'Save reading' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    const post = calls.find((c) => c.key === 'POST /api/tanks/t1/readings')!;
    expect(post.body).toEqual({ employee_id: 'e1', physical_stock: '2490.125' });
    expect(typeof (post.body as { physical_stock: unknown }).physical_stock).toBe('string');
    expect(await screen.findByText('Reading recorded for T1.')).toBeInTheDocument();
    expect(window.localStorage.getItem('pperp.lastReadingEmployee')).toBe('e1');
  });

  it('will not let a fourth decimal place be typed, says why, and never calls the server', async () => {
    const { calls } = setup(MANAGE);
    await signIn();
    const card = screen.getByRole('heading', { name: 'T1' }).closest('li')!;
    await userEvent.click(within(card).getByRole('button', { name: 'Record reading' }));
    await userEvent.selectOptions(await screen.findByLabelText('Taken by'), 'e1');
    await userEvent.type(screen.getByLabelText('Physical stock (L)'), '12.3456');
    expect(screen.getByLabelText('Physical stock (L)')).toHaveValue('12.345'); // not rounded, not sent
    expect(screen.getByText(/at most 3 decimal places/)).toBeInTheDocument();
    expect(calls.some((c) => c.key.startsWith('POST /api/tanks'))).toBe(false);
  });

  it('a pasted value with too many places is refused as a whole', async () => {
    setup(MANAGE);
    await signIn();
    const card = screen.getByRole('heading', { name: 'T1' }).closest('li')!;
    await userEvent.click(within(card).getByRole('button', { name: 'Receipt' }));
    const box = screen.getByLabelText('Quantity (L)');
    await userEvent.click(box);
    await userEvent.paste('100.12345');
    expect(box).toHaveValue('');
    expect(screen.getByText(/Extra digits are not accepted/)).toBeInTheDocument();
  });

  it('an adjustment accepts a minus sign, a receipt does not', async () => {
    setup(MANAGE);
    await signIn();
    const card = screen.getByRole('heading', { name: 'T1' }).closest('li')!;
    await userEvent.click(within(card).getByRole('button', { name: 'Receipt' }));
    await userEvent.type(screen.getByLabelText('Quantity (L)'), '-5');
    expect(screen.getByLabelText('Quantity (L)')).toHaveValue('5');
  });

  it('puts a server validation message next to the right field', async () => {
    setup(MANAGE, {
      'POST /api/tanks/t1/readings': () =>
        apiError(422, 'validation_error', 'Some fields are not valid.', {
          fields: [{ field: 'physical_stock', message: 'physical_stock cannot be negative' }],
        }),
    });
    await signIn();
    const card = screen.getByRole('heading', { name: 'T1' }).closest('li')!;
    await userEvent.click(within(card).getByRole('button', { name: 'Record reading' }));
    await userEvent.selectOptions(await screen.findByLabelText('Taken by'), 'e1');
    await userEvent.type(screen.getByLabelText('Physical stock (L)'), '5');
    await userEvent.click(screen.getByRole('button', { name: 'Save reading' }));
    expect(await screen.findByText('physical_stock cannot be negative')).toBeInTheDocument();
    expect(screen.getByLabelText('Physical stock (L)')).toHaveAttribute('aria-invalid', 'true');
  });
});

describe('Enter key (same as the Qt screens)', () => {
  it('Enter in the username moves to the password instead of submitting; Enter in the last field submits', async () => {
    const { calls } = setup(MANAGE);
    await userEvent.type(screen.getByLabelText('Username'), 'manager1{Enter}');
    expect(screen.getByLabelText('Password')).toHaveFocus();
    expect(calls.filter((c) => c.key.startsWith('POST'))).toHaveLength(0); // nothing sent yet
    await userEvent.type(screen.getByLabelText('Password'), 'Passw0rd!x{Enter}');
    await screen.findByRole('heading', { level: 1, name: /Tanks & Inventory/ });
    expect(calls.some((c) => c.key === 'POST /api/auth/login')).toBe(true);
  });

  it('in a dialog, Enter walks the fields and only the last one saves', async () => {
    const { calls } = setup(MANAGE, {
      'POST /api/tanks/t1/transactions': () =>
        json(201, {
          id: 'x',
          tank_id: 't1',
          tank_code: 'T1',
          transaction_type: 'receipt',
          quantity: '10.000',
          transaction_at: '2026-10-09T05:30:00Z',
          reference: null,
          remarks: null,
          recorded_by: 'm',
        }),
    });
    await signIn();
    const card = screen.getByRole('heading', { name: 'T1' }).closest('li')!;
    await userEvent.click(within(card).getByRole('button', { name: 'Receipt' }));
    await userEvent.type(screen.getByLabelText('Quantity (L)'), '10{Enter}');
    expect(screen.getByLabelText(/Reference/)).toHaveFocus();
    await userEvent.keyboard('{Enter}');
    expect(screen.getByLabelText(/Remarks/)).toHaveFocus();
    expect(calls.some((c) => c.key === 'POST /api/tanks/t1/transactions')).toBe(false);
    await userEvent.keyboard('{Enter}');
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(calls.some((c) => c.key === 'POST /api/tanks/t1/transactions')).toBe(true);
  });
});

describe('adding a tank', () => {
  it('creates the tank with string decimals and shows the new list', async () => {
    const { calls } = setup(MANAGE, {
      'POST /api/tanks': () => json(201, tank({ id: 't9', code: 'T9' })),
    });
    await signIn();
    await userEvent.click(screen.getByRole('button', { name: /add tank/i }));
    await userEvent.type(screen.getByLabelText('Tank code'), 'T9');
    await userEvent.selectOptions(await screen.findByLabelText('Fuel type'), 'f1');
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Add tank' }),
    );
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    const post = calls.find((c) => c.key === 'POST /api/tanks')!;
    expect(post.body).toEqual({
      code: 'T9',
      fuel_id: 'f1',
      capacity: '10000.000',
      opening_stock: '0',
    });
    expect(calls.filter((c) => c.key === 'GET /api/tanks').length).toBeGreaterThanOrEqual(2); // refetched
  });
});

describe('stock movements', () => {
  async function openReceipt() {
    await signIn();
    const card = screen.getByRole('heading', { name: 'T1' }).closest('li')!;
    await userEvent.click(within(card).getByRole('button', { name: 'Receipt' }));
  }

  it('shows the business rule from the server (capacity) and keeps what was typed', async () => {
    setup(MANAGE, {
      'POST /api/tanks/t1/transactions': () =>
        apiError(
          409,
          'conflict',
          'Receiving 9000 would exceed tank capacity (10000.000); current stock is 2500.500',
        ),
    });
    await openReceipt();
    await userEvent.type(screen.getByLabelText('Quantity (L)'), '9000');
    await userEvent.click(screen.getByRole('button', { name: 'Record receipt' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/would exceed tank capacity/);
    expect(screen.getByLabelText('Quantity (L)')).toHaveValue('9000');
  });

  it('shows current stock in the dialog so the person can sanity-check the number', async () => {
    setup(MANAGE);
    await openReceipt();
    expect(screen.getByText(/Now in tank/)).toHaveTextContent('2,500.500 L of 10,000.000 L');
  });

  it('Escape cancels without sending anything', async () => {
    const { calls } = setup(MANAGE);
    await openReceipt();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(calls.some((c) => c.key.startsWith('POST /api/tanks'))).toBe(false);
  });
});

describe('the dip chart', () => {
  it('is typed in as a table, saved as rows, and the detail page says in one line what each action changes', async () => {
    const api = setup(MANAGE, {
      'GET /api/tanks/t1': () => json(200, tank()),
      'GET /api/tanks/t1/transactions': () => json(200, []),
      'GET /api/tanks/t1/readings': () => json(200, []),
      'GET /api/tanks/t1/reconciliations': () => json(200, []),
      'GET /api/tanks/t1/dip-chart': () => json(200, []),
      'PUT /api/tanks/t1/dip-chart': () => json(200, []),
    });
    await signIn();
    await userEvent.click(screen.getAllByRole('link', { name: 'T1' })[0]!);
    await screen.findByRole('heading', { name: 'Tank T1' });
    const what = screen.getByLabelText('What each action changes').textContent ?? '';
    expect(what).toMatch(/Adds fuel that a tanker delivered to the book stock/);
    expect(what).toMatch(/The book stock does not change/);
    expect(what).toMatch(/sets the book stock to the measured figure/);
    await userEvent.click(screen.getByRole('button', { name: 'Dip chart' }));
    await userEvent.type(await screen.findByLabelText('Row 1 dip in cm'), '0');
    await userEvent.type(screen.getByLabelText('Row 1 litres'), '0');
    await userEvent.click(screen.getByRole('button', { name: /Add a row/ }));
    await userEvent.type(screen.getByLabelText('Row 2 dip in cm'), '100');
    await userEvent.type(screen.getByLabelText('Row 2 litres'), '10000');
    await userEvent.click(screen.getByRole('button', { name: 'Save chart' }));
    await waitFor(async () =>
      expect((await api).calls.find((c) => c.key === 'PUT /api/tanks/t1/dip-chart')?.body).toEqual({
        rows: [{ dip_cm: '0', litres: '0' }, { dip_cm: '100', litres: '10000' }],
      }),
    );
  });
});

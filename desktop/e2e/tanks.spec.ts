import { expect, signIn, test } from './fixtures';

test.describe('login', () => {
  test('wrong password shows the server message and stays on the sign-in screen', async ({
    launched,
  }) => {
    const { page } = launched;
    await signIn(page, 'manager1', 'not-the-password');
    await expect(page.getByRole('alert')).toContainText("isn't correct");
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  });

  test('a manager signs in and lands on the tanks', async ({ launched }) => {
    const { page } = launched;
    await signIn(page, 'manager1');
    await expect(page.getByRole('heading', { level: 1, name: /Tanks & Inventory/ })).toBeVisible();
    await expect(page.getByText('Signed in as')).toContainText('Manager1');
  });
});

test.describe('viewing tanks', () => {
  test('shows each tank with its exact stock, fill level and status', async ({ launched }) => {
    const { page } = launched;
    await signIn(page, 'manager1');
    const t1 = page
      .getByRole('listitem')
      .filter({ has: page.getByRole('heading', { name: 'T1' }) });
    await expect(t1.getByText('2,500.500')).toBeVisible();
    await expect(t1.getByText('of 10,000.000 L')).toBeVisible();
    await expect(t1.getByRole('meter')).toHaveAttribute('aria-valuetext', '25.0%');
    const t2 = page
      .getByRole('listitem')
      .filter({ has: page.getByRole('heading', { name: 'T2' }) });
    await expect(t2.getByText(/Low - 18\.0%/)).toBeVisible();
  });

  test('switches to the table view and opens a tank', async ({ launched }) => {
    const { page } = launched;
    await signIn(page, 'manager1');
    await page.getByRole('button', { name: 'Table' }).click();
    await expect(page.getByRole('table', { name: 'All tanks' })).toBeVisible();
    await page.getByRole('link', { name: 'T1' }).click();
    await expect(page.getByRole('heading', { name: 'Tank T1' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Transactions' })).toBeVisible();
  });
});

test.describe('recording', () => {
  test('a manager records a dip reading and sees it in the history', async ({ launched }) => {
    const { page } = launched;
    await signIn(page, 'manager1');
    const t1 = page
      .getByRole('listitem')
      .filter({ has: page.getByRole('heading', { name: 'T1' }) });
    await t1.getByRole('button', { name: 'Record reading' }).click();
    const dialog = page.getByRole('dialog', { name: /Record reading - T1/ });
    await dialog.getByLabel('Taken by').selectOption({ label: 'EMP-0001 - Ravi Kumar' });
    await dialog.getByLabel('Physical stock (L)').fill('2490.125');
    await dialog.getByRole('button', { name: 'Save reading' }).click();
    await expect(page.getByRole('status')).toContainText('Reading recorded for T1.');
    await expect(dialog).toBeHidden();

    await t1.getByRole('link', { name: 'Open' }).click();
    await page.getByRole('tab', { name: 'Readings' }).click();
    const row = page.getByRole('row').filter({ hasText: 'Ravi Kumar' });
    await expect(row).toContainText('2,490.125');
    // A reading is an observation: the book stock is unchanged.
    await expect(page.getByText('2,500.500').first()).toBeVisible();
  });

  test('a receipt moves the stock, and a rule violation is explained without losing the form', async ({
    launched,
  }) => {
    const { page } = launched;
    await signIn(page, 'manager1');
    const t1 = page
      .getByRole('listitem')
      .filter({ has: page.getByRole('heading', { name: 'T1' }) });
    await t1.getByRole('button', { name: 'Receipt' }).click();
    const dialog = page.getByRole('dialog');
    await dialog.getByLabel('Quantity (L)').fill('9000');
    await dialog.getByRole('button', { name: 'Record receipt' }).click();
    await expect(dialog.getByRole('alert')).toContainText('would exceed tank capacity');
    await expect(dialog.getByLabel('Quantity (L)')).toHaveValue('9000');

    await dialog.getByLabel('Quantity (L)').fill('1000.5');
    await dialog.getByLabel('Reference').fill('INV-77');
    await dialog.getByRole('button', { name: 'Record receipt' }).click();
    await expect(dialog).toBeHidden();
    await expect(t1.getByText('3,501.000')).toBeVisible();
  });

  test('reconciling resets the book stock and reports the variance', async ({ launched }) => {
    const { page } = launched;
    await signIn(page, 'manager1');
    await page.getByRole('link', { name: 'Open' }).first().click();
    await page.getByRole('button', { name: 'Reconcile' }).click();
    const dialog = page.getByRole('dialog', { name: /Reconcile - T1/ });
    await dialog.getByLabel('Physical stock (L)').fill('2490.500');
    await dialog.getByRole('button', { name: 'Reconcile' }).click();
    await expect(page.getByRole('dialog', { name: 'Reconciliation complete' })).toContainText(
      '-10.000',
    );
    await page.getByRole('button', { name: 'Done' }).click();
    await page.getByRole('tab', { name: 'Reconciliation' }).click();
    await expect(page.getByText(/Latest reconciliation/)).toBeVisible();
  });
});

test.describe('permissions', () => {
  test('a view-only accountant can look but not change', async ({ launched }) => {
    const { page } = launched;
    await signIn(page, 'accountant1');
    await expect(page.getByRole('heading', { name: 'T1' })).toBeVisible();
    await expect(page.getByRole('button', { name: /add tank/i })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Record reading' })).toHaveCount(0);
    await page.getByRole('link', { name: 'Open' }).first().click();
    for (const name of [
      'Receipt',
      'Issue',
      'Adjustment',
      'Record reading',
      'Reconcile',
      'Change status',
    ]) {
      await expect(page.getByRole('button', { name, exact: true })).toBeDisabled();
    }
  });

  test('the server itself refuses a forbidden write (hiding the button is not the security)', async ({
    launched,
  }) => {
    const { page } = launched;
    await signIn(page, 'accountant1');
    await expect(page.getByRole('heading', { name: 'T1' })).toBeVisible();
    const result = await page.evaluate(async () => {
      const bridge = window.pperp!;
      const login = await fetch(`${bridge.apiBase}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Launch-Secret': bridge.launchSecret },
        body: JSON.stringify({ username: 'accountant1', password: 'Passw0rd!x' }),
      }).then((r) => r.json());
      const tanks = await fetch(`${bridge.apiBase}/api/tanks`, {
        headers: { Authorization: `Bearer ${login.token}`, 'X-Launch-Secret': bridge.launchSecret },
      }).then((r) => r.json());
      const res = await fetch(`${bridge.apiBase}/api/tanks/${tanks[0].id}/transactions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${login.token}`,
          'X-Launch-Secret': bridge.launchSecret,
        },
        body: JSON.stringify({ transaction_type: 'receipt', quantity: '5' }),
      });
      return { status: res.status, body: await res.json() };
    });
    expect(result.status).toBe(403);
    expect(result.body.error.code).toBe('permission_denied');
  });

  test('an attendant has no tanks access and is told so', async ({ launched }) => {
    const { page } = launched;
    await signIn(page, 'attendant1');
    // The role has no inventory permission, so the sidebar has no Tanks link; going there directly is refused by the server.
    await expect(
      page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Tanks' }),
    ).toHaveCount(0);
    await page.evaluate(() => {
      location.hash = '#/tanks';
    });
    await expect(page.getByText('You do not have access to this')).toBeVisible();
  });
});

test.describe('logout and one instance of the module', () => {
  test('logging out returns to the sign-in screen and a fresh sign-in works', async ({
    launched,
  }) => {
    const { page } = launched;
    await signIn(page, 'manager1');
    await expect(page.getByRole('heading', { name: 'T1' })).toBeVisible();
    await page.getByRole('button', { name: 'Log out' }).click();
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'T1' })).toHaveCount(0);
    await signIn(page, 'manager1');
    await expect(page.getByRole('heading', { name: 'T1' })).toBeVisible();
  });

  test('after logout the server rejects the old session token', async ({ launched }) => {
    const { page } = launched;
    const statuses = await page.evaluate(async () => {
      const b = window.pperp!;
      const headers = { 'Content-Type': 'application/json', 'X-Launch-Secret': b.launchSecret };
      const login = await fetch(`${b.apiBase}/api/auth/login`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ username: 'manager1', password: 'Passw0rd!x' }),
      }).then((r) => r.json());
      const auth = { ...headers, Authorization: `Bearer ${login.token}` };
      const before = (await fetch(`${b.apiBase}/api/tanks`, { headers: auth })).status;
      const logout = (
        await fetch(`${b.apiBase}/api/auth/logout`, { method: 'POST', headers: auth, body: '{}' })
      ).status;
      const after = (await fetch(`${b.apiBase}/api/tanks`, { headers: auth })).status;
      return { before, logout, after };
    });
    expect(statuses).toEqual({ before: 200, logout: 204, after: 401 });
  });

  test('opening Tanks repeatedly never creates a second copy or a second window', async ({
    launched,
  }) => {
    const { page, app } = launched;
    await signIn(page, 'manager1');
    const nav = page.getByRole('navigation', { name: 'Main' });
    for (let i = 0; i < 5; i++) await nav.getByRole('link', { name: 'Tanks' }).click();
    await expect(page.getByRole('heading', { level: 1, name: /Tanks & Inventory/ })).toHaveCount(1);
    await page.getByRole('button', { name: /add tank/i }).dblclick();
    await expect(page.getByRole('dialog')).toHaveCount(1);
    expect(app.windows()).toHaveLength(1);
  });
});

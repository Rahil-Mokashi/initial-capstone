import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { apiError, json } from '@/test/mockApi';

const u = (over: Record<string, unknown> = {}) => ({
  id: 'u2',
  username: 'ravi',
  email: 'ravi@example.com',
  first_name: null,
  last_name: null,
  role_id: 'r1',
  role: 'ATTENDANT',
  is_active: true,
  is_locked: false,
  status: 'Active',
  last_login: null,
  ...over,
});
const ROLES = [
  { id: 'r1', name: 'ATTENDANT' },
  { id: 'r2', name: 'MANAGER' },
];
const base = () => ({
  'GET /api/users': () =>
    json(200, [u(), u({ id: 'u3', username: 'locky', status: 'Locked', is_locked: true })]),
  'GET /api/users/roles': () => json(200, ROLES),
});

beforeEach(() => session.set(null));
afterEach(() => vi.unstubAllGlobals());

describe('users list and add', () => {
  it('lists users with status words and adds one with a role', async () => {
    const api = await openAs(['user.manage'], '/users', 'Users', {
      ...base(),
      'POST /api/users': () => json(201, u({ id: 'u9', username: 'newbie' })),
    });
    expect(await screen.findByRole('link', { name: 'ravi' })).toBeInTheDocument();
    expect(screen.getByText('Locked')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Add user/ }));
    const d = screen.getByRole('dialog');
    await userEvent.click(within(d).getByRole('button', { name: 'Save' }));
    expect(await within(d).findByText('Enter a username.')).toBeInTheDocument();
    await userEvent.type(within(d).getByLabelText('Username'), 'newbie');
    await userEvent.type(within(d).getByLabelText('Email'), 'n@example.com');
    await userEvent.type(within(d).getByLabelText('Password'), 'Str0ngPass!x');
    await userEvent.selectOptions(await within(d).findByLabelText('Role'), 'r2');
    await userEvent.click(within(d).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.calls.find((c) => c.key === 'POST /api/users')?.body).toEqual({
      username: 'newbie',
      email: 'n@example.com',
      password: 'Str0ngPass!x',
      role_id: 'r2',
    });
  });

  it('shows the server field error beside the field', async () => {
    await openAs(['user.manage'], '/users', 'Users', {
      ...base(),
      'POST /api/users': () =>
        apiError(422, 'validation_error', 'Some fields are not valid.', {
          fields: [{ field: 'password', message: 'Password is too weak.' }],
        }),
    });
    await userEvent.click(await screen.findByRole('button', { name: /Add user/ }));
    const d = screen.getByRole('dialog');
    await userEvent.type(within(d).getByLabelText('Username'), 'newbie');
    await userEvent.type(within(d).getByLabelText('Email'), 'n@example.com');
    await userEvent.type(within(d).getByLabelText('Password'), 'x');
    await userEvent.selectOptions(await within(d).findByLabelText('Role'), 'r1');
    await userEvent.click(within(d).getByRole('button', { name: 'Save' }));
    expect(await within(d).findByText('Password is too weak.')).toBeInTheDocument();
  });

  it('a user without user.manage is told so', async () => {
    await openAs(['inventory.view'], '/users', 'Users', {
      'GET /api/users': () =>
        apiError(403, 'permission_denied', 'no', { permission: 'user.manage' }),
    });
    expect(await screen.findByText('You do not have access to this')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Add user/ })).not.toBeInTheDocument();
  });
});

describe('user detail actions', () => {
  it('deactivates with no reason typed, unlock is disabled unless locked, reset code is shown once', async () => {
    const api = await openAs(['user.manage'], '/users/u2', 'ravi', {
      ...base(),
      'POST /api/users/u2/active': () => json(200, u({ is_active: false, status: 'Inactive' })),
      'POST /api/users/u2/reset-code': () => json(200, { code: 'ABC12345' }),
    });
    expect(screen.getByRole('button', { name: /Unlock account/ })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Deactivate' }));
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Deactivate' }),
    );
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/users/u2/active')?.body).toEqual({
        is_active: false,
        reason: '',
      }),
    );
    await userEvent.click(screen.getByRole('button', { name: 'Generate password reset code' }));
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Generate code' }),
    );
    expect(await screen.findByLabelText('Reset code')).toHaveTextContent('ABC12345');
  });

  it('resets a password and changes a role', async () => {
    const api = await openAs(['user.manage'], '/users/u2', 'ravi', {
      ...base(),
      'POST /api/users/u2/reset-password': () => json(200, u()),
      'POST /api/users/u2/role': () => json(200, u({ role: 'MANAGER', role_id: 'r2' })),
    });
    await userEvent.click(screen.getByRole('button', { name: /Reset password/ }));
    let d = screen.getByRole('dialog');
    await userEvent.click(within(d).getByRole('button', { name: 'Reset password' }));
    expect(await within(d).findByText('Enter a temporary password.')).toBeInTheDocument();
    await userEvent.type(within(d).getByLabelText('New temporary password'), 'Temp0rary!x9');
    await userEvent.click(within(d).getByRole('button', { name: 'Reset password' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.calls.find((c) => c.key === 'POST /api/users/u2/reset-password')?.body).toEqual({
      new_password: 'Temp0rary!x9',
      reason: '',
    });
    await userEvent.click(screen.getByRole('button', { name: /Change role/ }));
    d = screen.getByRole('dialog');
    await userEvent.selectOptions(await within(d).findByLabelText('Role'), 'r2');
    await userEvent.click(within(d).getByRole('button', { name: 'Change role' }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/users/u2/role')?.body).toEqual({
        role_id: 'r2',
        reason: '',
      }),
    );
  });

  it('unlocks a locked account', async () => {
    const api = await openAs(['user.manage'], '/users/u3', 'locky', {
      ...base(),
      'POST /api/users/u3/unlock': () => json(200, u({ id: 'u3', username: 'locky' })),
    });
    await userEvent.click(screen.getByRole('button', { name: /Unlock account/ }));
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Unlock' }),
    );
    await waitFor(() =>
      expect(api.calls.some((c) => c.key === 'POST /api/users/u3/unlock')).toBe(true),
    );
  });
});

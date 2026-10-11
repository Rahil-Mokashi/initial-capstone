import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { secondsUntil } from '@/features/auth/LoginPage';
import { renderApp } from '@/test/harness';
import { apiError, json, user } from '@/test/mockApi';

const ok =
  (permissions = ['inventory.view'], over: Record<string, unknown> = {}) =>
  () =>
    json(200, { token: 'tok', expires_at: '2099-01-01T00:00:00', user: user(permissions, over) });

beforeEach(() => {
  session.set(null);
  window.localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
});
afterEach(() => vi.unstubAllGlobals());

describe('sign-in screen', () => {
  it('shows the device name and the welcome text, in English by default', async () => {
    renderApp('/login', {});
    expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
    expect(await screen.findByText(/Device: TEST-PC/)).toBeInTheDocument();
  });

  it('switches to Hindi, remembers it for the next visit, and switches back', async () => {
    renderApp('/login', {});
    await userEvent.click(await screen.findByRole('button', { name: 'Switch to Hindi' }));
    expect(screen.getByRole('heading', { name: 'वापसी पर स्वागत है' })).toBeInTheDocument();
    expect(window.localStorage.getItem('pperp.loginLocale')).toBe('hi');
    await userEvent.click(screen.getByRole('button', { name: 'Switch to English' }));
    expect(screen.getByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
  });

  it('signs in with a PIN: the toggle swaps the field and sends use_pin', async () => {
    const api = renderApp('/login', { 'POST /api/auth/login': ok() });
    await userEvent.type(await screen.findByLabelText('Username'), 'manager1');
    await userEvent.click(screen.getByRole('button', { name: 'Use PIN instead' }));
    const pin = screen.getByLabelText('PIN');
    expect(pin).toHaveAttribute('inputmode', 'numeric');
    await userEvent.type(pin, '483920');
    await userEvent.click(screen.getByRole('button', { name: /^Sign in/i }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'POST /api/auth/login')?.body).toEqual({
        username: 'manager1',
        password: '483920',
        use_pin: true,
      }),
    );
  });

  it('asks for the right thing when empty, and never calls the server', async () => {
    const api = renderApp('/login', {});
    await userEvent.click(await screen.findByRole('button', { name: /^Sign in/i }));
    expect(await screen.findByText('Username is required.')).toBeInTheDocument();
    expect(screen.getByText('Password is required.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Use PIN instead' }));
    await userEvent.click(screen.getByRole('button', { name: /^Sign in/i }));
    expect(await screen.findByText('PIN is required.')).toBeInTheDocument();
    expect(api.calls.some((c) => c.key === 'POST /api/auth/login')).toBe(false);
  });

  it('warns when Caps Lock is on, and can show the password', async () => {
    renderApp('/login', {});
    const pw = await screen.findByLabelText('Password');
    expect(pw).toHaveAttribute('type', 'password');
    // jsdom has no real Caps Lock state; the handler reads getModifierState, so drive it directly
    const evt = new KeyboardEvent('keydown', { key: 'a', bubbles: true });
    Object.defineProperty(evt, 'getModifierState', { value: (k: string) => k === 'CapsLock' });
    pw.dispatchEvent(evt);
    expect(await screen.findByText('Caps Lock is on.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Show' }));
    expect(pw).toHaveAttribute('type', 'text');
    expect(screen.getByRole('button', { name: 'Hide' })).toBeInTheDocument();
  });

  it('shows how many attempts are left, then the lockout countdown (sign-in is blocked meanwhile)', async () => {
    const until = new Date(Date.now() + 90_000).toISOString();
    let n = 0;
    renderApp('/login', {
      'POST /api/auth/login': () =>
        n++ === 0
          ? apiError(401, 'invalid_credentials', 'That username or password is not correct.', {
              attempts_remaining: 2,
            })
          : apiError(401, 'account_locked', 'This account is locked.', { locked_until: until }),
    });
    await userEvent.type(await screen.findByLabelText('Username'), 'manager1');
    await userEvent.type(screen.getByLabelText('Password'), 'wrong');
    await userEvent.click(screen.getByRole('button', { name: /^Sign in/i }));
    const first = await screen.findByRole('alert');
    expect(first).toHaveTextContent('is not correct');
    expect(first).toHaveTextContent('2 attempts left before this account is locked.');
    await userEvent.type(screen.getByLabelText('Password'), 'wrong2');
    await userEvent.click(screen.getByRole('button', { name: /^Sign in/i }));
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/Try again in 1:[23]\d\./),
    );
    expect(screen.getByRole('button', { name: /^Sign in/i })).toBeDisabled();
  });

  it('remembers usernames that signed in successfully', async () => {
    renderApp('/login', { 'POST /api/auth/login': ok() });
    await userEvent.type(await screen.findByLabelText('Username'), 'manager1');
    await userEvent.type(screen.getByLabelText('Password'), 'Passw0rd!x');
    await userEvent.click(screen.getByRole('button', { name: /^Sign in/i }));
    await waitFor(() =>
      expect(window.localStorage.getItem('pperp.recentUsernames')).toBe('["manager1"]'),
    );
  });

  it('the theme button flips light / dark and remembers it', async () => {
    renderApp('/login', {});
    await userEvent.click(
      await screen.findByRole('button', { name: /Switch to (dark|light) theme/ }),
    );
    const applied = document.documentElement.getAttribute('data-theme');
    expect(['dark', 'light']).toContain(applied);
    expect(window.localStorage.getItem('pperp.theme')).toBe(applied);
  });
});

describe('forgot password', () => {
  it('finishes an admin-issued code without a session, checking the two passwords match', async () => {
    const api = renderApp('/login', { 'POST /api/auth/forgot-password': () => ({ status: 204 }) });
    await userEvent.click(await screen.findByRole('button', { name: 'Forgot password?' }));
    const d = screen.getByRole('dialog');
    await userEvent.type(within(d).getByLabelText('Username'), 'attendant1');
    await userEvent.type(within(d).getByLabelText('Reset code'), '12345678');
    await userEvent.type(within(d).getByLabelText('New password'), 'N3w!Passw0rd');
    await userEvent.type(within(d).getByLabelText('Confirm new password'), 'different');
    await userEvent.click(within(d).getByRole('button', { name: 'Reset password' }));
    expect(
      await within(d).findByText('New password and confirmation do not match.'),
    ).toBeInTheDocument();
    await userEvent.clear(within(d).getByLabelText('Confirm new password'));
    await userEvent.type(within(d).getByLabelText('Confirm new password'), 'N3w!Passw0rd');
    await userEvent.click(within(d).getByRole('button', { name: 'Reset password' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.calls.find((c) => c.key === 'POST /api/auth/forgot-password')?.body).toEqual({
      username: 'attendant1',
      code: '12345678',
      new_password: 'N3w!Passw0rd',
    });
  });

  it('shows the server refusal inside the dialog', async () => {
    renderApp('/login', {
      'POST /api/auth/forgot-password': () =>
        apiError(401, 'authentication_failed', 'That reset code is not valid or has expired.'),
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Forgot password?' }));
    const d = screen.getByRole('dialog');
    await userEvent.type(within(d).getByLabelText('Username'), 'x');
    await userEvent.type(within(d).getByLabelText('Reset code'), '1');
    await userEvent.type(within(d).getByLabelText('New password'), 'N3w!Passw0rd');
    await userEvent.type(within(d).getByLabelText('Confirm new password'), 'N3w!Passw0rd');
    await userEvent.click(within(d).getByRole('button', { name: 'Reset password' }));
    expect(await within(d).findByRole('alert')).toHaveTextContent('not valid or has expired');
  });
});

describe('secondsUntil', () => {
  it('counts whole seconds, never below zero, and tolerates a missing or odd value', () => {
    const now = Date.parse('2026-10-11T10:00:00Z');
    expect(secondsUntil('2026-10-11T10:01:30Z', now)).toBe(90);
    expect(secondsUntil('2026-10-11T10:01:30', now)).toBe(90); // the server omits the zone: UTC
    expect(secondsUntil('2026-10-11T09:00:00Z', now)).toBe(0);
    expect(secondsUntil(undefined, now)).toBe(0);
    expect(secondsUntil('not a date', now)).toBe(0);
  });
});

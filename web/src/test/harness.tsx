import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { App } from '@/App';
import { AuthProvider } from '@/auth/AuthContext';
import { ToastProvider } from '@/components/ui/Toast';
import { json, mockApi, user } from './mockApi';

/** Renders the whole app at `path` against mocked API routes, signed out. */
export function renderApp(path: string, routes: Parameters<typeof mockApi>[0] = {}) {
  const api = mockApi({
    'POST /api/auth/logout': () => ({ status: 204 }),
    ...routes,
  });
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
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

/**
 * Renders the whole app at `path`, signs in as a user holding `permissions` and waits for `ready`
 * (a heading name). Opening a protected path while signed out sends the user to sign in, then back to it.
 */
export async function openAs(
  permissions: string[],
  path: string,
  ready: string | RegExp,
  routes: Parameters<typeof mockApi>[0] = {},
  userOver: Record<string, unknown> = {},
) {
  const api = renderApp(path, {
    'POST /api/auth/login': () =>
      json(200, {
        token: 'tok',
        expires_at: '2099-01-01T00:00:00',
        user: user(permissions, userOver),
      }),
    ...routes,
  });
  await userEvent.type(await screen.findByLabelText('Username'), 'manager1');
  await userEvent.type(screen.getByLabelText('Password'), 'Passw0rd!x');
  await userEvent.click(screen.getByRole('button', { name: /^Sign in/i }));
  await screen.findByRole('heading', { name: ready });
  return api;
}

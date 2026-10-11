import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { App } from '@/App';
import { AuthProvider } from '@/auth/AuthContext';
import { ToastProvider } from '@/components/ui/Toast';
import { apiError, json, mockApi, user } from '@/test/mockApi';

const MANAGE = ['fuel_price.view', 'fuel_price.manage'];
const fuel = (over: Record<string, unknown> = {}) => ({
  id: 'f1',
  fuel_type: 'Petrol',
  rate_per_liter: '0.00',
  priced: false,
  ...over,
});

async function setup(permissions: string[], extra: Parameters<typeof mockApi>[0] = {}) {
  const api = mockApi({
    'POST /api/auth/login': () =>
      json(200, { token: 'tok', expires_at: '2099-01-01T00:00:00', user: user(permissions) }),
    'GET /api/fuel-prices': () =>
      json(200, [
        fuel(),
        fuel({ id: 'f2', fuel_type: 'Diesel', rate_per_liter: '92.10', priced: true }),
      ]),
    ...extra,
  });
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <ToastProvider>
        <AuthProvider>
          <MemoryRouter initialEntries={['/fuel-prices']}>
            <App />
          </MemoryRouter>
        </AuthProvider>
      </ToastProvider>
    </QueryClientProvider>,
  );
  await userEvent.type(await screen.findByLabelText('Username'), 'manager1');
  await userEvent.type(screen.getByLabelText('Password'), 'Passw0rd!x');
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
  await screen.findByRole('heading', { level: 1, name: 'Fuel Prices' });
  return api;
}

beforeEach(() => session.set(null));
afterEach(() => vi.unstubAllGlobals());

describe('fuel prices', () => {
  it('shows priced and unpriced fuels and warns about the unpriced one', async () => {
    await setup(MANAGE);
    const row = await screen.findByRole('row', { name: /Petrol/ });
    expect(within(row).getByText('No price set')).toBeInTheDocument();
    expect(
      within(screen.getByRole('row', { name: /Diesel/ })).getByText('₹92.10'),
    ).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('1 fuel type(s) have no selling price');
  });

  it('changes a price: reason required, string rate sent, extra decimals refused', async () => {
    const api = await setup(MANAGE, {
      'POST /api/fuel-prices/f1/rate': () =>
        json(200, fuel({ rate_per_liter: '104.50', priced: true })),
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Change price of Petrol' }));
    const dialog = screen.getByRole('dialog');
    const rate = within(dialog).getByLabelText('New rate per litre');
    expect(rate).toHaveValue('100.00'); // Qt's default for an unpriced fuel
    await userEvent.clear(rate);
    await userEvent.type(rate, '104.505');
    expect(rate).toHaveValue('104.50'); // third decimal refused, never rounded
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    expect(await within(dialog).findByText('Give a reason for the change.')).toBeInTheDocument();
    await userEvent.type(within(dialog).getByLabelText('Reason'), 'OMC revision');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.calls.find((c) => c.key === 'POST /api/fuel-prices/f1/rate')?.body).toEqual({
      new_rate_per_liter: '104.50',
      reason: 'OMC revision',
    });
  });

  it('shows a server conflict inside the dialog and keeps the typed values', async () => {
    await setup(MANAGE, {
      'POST /api/fuel-prices/f2/rate': () =>
        apiError(409, 'conflict', 'Diesel is already priced at 92.10; no change to record'),
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Change price of Diesel' }));
    const dialog = screen.getByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText('Reason'), 'same');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('already priced');
    expect(within(dialog).getByLabelText('Reason')).toHaveValue('same');
  });

  it('shows the history and hides change buttons from a view-only user', async () => {
    await setup(['fuel_price.view'], {
      'GET /api/fuel-prices/f2/history': () =>
        json(200, [
          {
            id: 'h1',
            effective_from: '2026-10-01T08:00:00Z',
            old_rate_per_liter: null,
            new_rate_per_liter: '92.10',
            reason: 'First price',
          },
        ]),
    });
    expect(screen.queryByRole('button', { name: /Change price/ })).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole('button', { name: 'Price history for Diesel' }));
    expect(await screen.findByText('First price')).toBeInTheDocument();
  });
});

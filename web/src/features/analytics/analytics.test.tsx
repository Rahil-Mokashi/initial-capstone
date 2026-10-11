import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { apiError, json } from '@/test/mockApi';

const performance = (title = 'Business Performance - Day (2026-10-11 to 2026-10-11)') => ({
  title,
  headers: [
    'Fuel Type',
    'Revenue',
    'Quantity (L)',
    'Avg. Cost',
    'Est. Cost of Goods',
    'Est. Gross Profit',
    'Margin %',
  ],
  rows: [
    ['Petrol', '1000.00', '10.00', 'N/A', 'N/A', 'N/A', 'N/A'],
    ['Total Revenue', '1000.00', '', '', '', '', ''],
  ],
  money_columns: [],
  volume_columns: [],
  html: '<table>performance</table>',
});
const forecast = {
  report: {
    title: 'Sales Forecast',
    headers: [
      'Fuel Type',
      'Trend',
      'Predicted Next Week (L)',
      'Predicted Revenue',
      'Change vs Last Week',
    ],
    rows: [['Petrol', 'Not enough data', 'N/A', 'N/A', 'N/A']],
    money_columns: [],
    volume_columns: [],
    html: '<table>forecast</table><p>Petrol: not enough history yet.</p>',
  },
  explanations: ['Petrol: not enough history yet.'],
};

beforeEach(() => session.set(null));
afterEach(() => {
  vi.unstubAllGlobals();
  delete window.pperp;
});

describe('business insights', () => {
  it('shows performance for the chosen period only after Generate, with the profit note', async () => {
    const api = await openAs(['analytics.view'], '/analytics', 'Business Insights', {
      'GET /api/analytics/performance': () => json(200, performance()),
      'GET /api/analytics/forecast': () => json(200, forecast),
    });
    expect(
      await screen.findByRole('table', { name: /Business Performance - Day/ }),
    ).toBeInTheDocument();
    expect(screen.getByText(/weighted-average purchase cost/)).toBeInTheDocument();
    expect(screen.getAllByText('N/A').length).toBeGreaterThan(0);
    await userEvent.selectOptions(screen.getByLabelText('Period'), 'quarter');
    // choosing alone does not query
    expect(api.calls.filter((c) => c.key === 'GET /api/analytics/performance')).toHaveLength(1);
    await userEvent.click(screen.getByRole('button', { name: /Generate/ }));
    await waitFor(() => {
      const urls = (
        globalThis.fetch as unknown as { mock: { calls: Array<[RequestInfo | URL]> } }
      ).mock.calls.map((c) => String(c[0]));
      expect(urls.some((u) => u.includes('/analytics/performance?period=quarter&as_of='))).toBe(
        true,
      );
    });
  });

  it('prints the performance report and exports it', async () => {
    const preview = vi.fn(async () => ({ ok: true }));
    const save = vi.fn(async () => ({ ok: true, path: 'C:\\out\\x.pdf' }));
    window.pperp = {
      apiBase: '',
      launchSecret: 's',
      files: { pickPath: async () => null, save },
      print: { preview },
    } as never;
    await openAs(['analytics.view'], '/analytics', 'Business Insights', {
      'GET /api/analytics/performance': () => json(200, performance()),
      'GET /api/analytics/forecast': () => json(200, forecast),
    });
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    const original = fetchMock.getMockImplementation() as unknown as (
      i: RequestInfo | URL,
      init?: RequestInit,
    ) => Promise<Response>;
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) =>
      String(input).includes('/export.pdf')
        ? new Response(new Uint8Array([0x25, 0x50, 0x44, 0x46]), { status: 200 })
        : original(input, init),
    );
    await screen.findByRole('table', { name: /Business Performance/ });
    await userEvent.click(screen.getByRole('button', { name: 'Print' }));
    await waitFor(() =>
      expect(preview).toHaveBeenCalledWith('<table>performance</table>', undefined),
    );
    await userEvent.click(screen.getByRole('button', { name: 'Export PDF' }));
    await waitFor(() =>
      expect(save).toHaveBeenCalledWith('business_performance.pdf', btoa('%PDF')),
    );
    expect(screen.getByRole('button', { name: 'Export Excel' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Export CSV' })).toBeInTheDocument();
  });

  it('shows the forecast table with one explanation per fuel, and prints them after the table', async () => {
    const preview = vi.fn(async () => ({ ok: true }));
    window.pperp = {
      apiBase: '',
      launchSecret: 's',
      files: { pickPath: async () => null, save: async () => ({ ok: true }) },
      print: { preview },
    } as never;
    await openAs(['analytics.view'], '/analytics', 'Business Insights', {
      'GET /api/analytics/performance': () => json(200, performance()),
      'GET /api/analytics/forecast': () => json(200, forecast),
    });
    await userEvent.click(await screen.findByRole('tab', { name: 'Sales Forecast' }));
    expect(await screen.findByRole('table', { name: 'Sales Forecast' })).toBeInTheDocument();
    expect(screen.getByText('Petrol: not enough history yet.')).toBeInTheDocument();
    const printButtons = screen.getAllByRole('button', { name: 'Print' });
    await userEvent.click(printButtons[printButtons.length - 1]!);
    await waitFor(() => expect(preview).toHaveBeenCalledWith(forecast.report.html, undefined));
  });

  it('shows a permission message to someone without analytics.view', async () => {
    await openAs(['sale.view'], '/analytics', 'Business Insights', {
      'GET /api/analytics/performance': () =>
        apiError(403, 'permission_denied', 'no', { permission: 'analytics.view' }),
      'GET /api/analytics/forecast': () =>
        apiError(403, 'permission_denied', 'no', { permission: 'analytics.view' }),
    });
    expect(await screen.findByText('You do not have access to this')).toBeInTheDocument();
  });
});

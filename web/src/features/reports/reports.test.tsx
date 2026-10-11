import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { json } from '@/test/mockApi';

const hub = (over: Record<string, unknown> = {}) => ({
  reports: [
    { key: 'sales_report', label: 'Sales Report', dates: true, filters: [] },
    {
      key: 'attendant_nozzle_report',
      label: 'Attendant & Nozzle Report',
      dates: true,
      filters: ['employee', 'nozzle'],
    },
    { key: 'fuel_type_summary', label: 'Fuel Type Summary', dates: false, filters: [] },
  ],
  insights: true,
  ...over,
});
const sales = {
  title: 'Sales Report',
  headers: ['Fuel Type', 'Sales', 'Quantity (L)', 'Amount'],
  rows: [
    ['Petrol', '2', '12345.50', '1234567.00'],
    ['Total', '2', '12345.50', '1234567.00'],
  ],
  money_columns: [3],
  volume_columns: [2],
  html: '<table>sales</table>',
};

beforeEach(() => session.set(null));
afterEach(() => {
  vi.unstubAllGlobals();
  delete window.pperp;
});

describe('reports hub', () => {
  it('lists only the reports the role may open, plus Business Insights when allowed', async () => {
    await openAs(['sale.view'], '/reports', 'Reports', {
      'GET /api/reports': () => json(200, hub()),
    });
    expect(await screen.findByRole('link', { name: 'Sales Report' })).toHaveAttribute(
      'href',
      '/reports/sales_report',
    );
    expect(screen.getByRole('link', { name: /Business Insights/ })).toBeInTheDocument();
  });

  it('says so when no report is available', async () => {
    await openAs(['sale.view'], '/reports', 'Reports', {
      'GET /api/reports': () => json(200, hub({ reports: [], insights: false })),
    });
    expect(await screen.findByText('No reports available for your role yet.')).toBeInTheDocument();
  });
});

describe('a table report', () => {
  const routes = (extra: Parameters<typeof openAs>[3] = {}) => ({
    'GET /api/reports': () => json(200, hub()),
    'GET /api/reports/filter-options': () =>
      json(200, {
        employees: [{ label: 'EMP-0001 - Ravi Kumar', value: 'e1' }],
        nozzles: [{ label: 'N1', value: 'n1' }],
      }),
    'GET /api/reports/sales_report': () => json(200, sales),
    'GET /api/reports/attendant_nozzle_report': () =>
      json(200, { ...sales, title: 'Attendant & Nozzle Report' }),
    ...extra,
  });

  it('right-aligns money and litre columns with Indian digit grouping', async () => {
    await openAs(['sale.view'], '/reports/sales_report', 'Sales Report', routes());
    const table = await screen.findByRole('table', { name: 'Sales Report' });
    expect(within(table).getAllByText('12,345.50')).toHaveLength(2);
    expect(within(table).getAllByText('12,34,567.00')).toHaveLength(2); // lakh grouping
  });

  it('Refresh applies the dates; blank dates are never sent', async () => {
    const api = await openAs(['sale.view'], '/reports/sales_report', 'Sales Report', routes());
    await screen.findByRole('table', { name: 'Sales Report' });
    expect(api.calls.filter((c) => c.key === 'GET /api/reports/sales_report')).toHaveLength(1);
    await userEvent.type(screen.getByLabelText('From'), '2026-10-01');
    // typing alone does not re-query; Refresh does (as in Qt)
    expect(api.calls.filter((c) => c.key === 'GET /api/reports/sales_report')).toHaveLength(1);
    await userEvent.click(screen.getByRole('button', { name: /Refresh/ }));
    await waitFor(() =>
      expect(api.calls.filter((c) => c.key === 'GET /api/reports/sales_report')).toHaveLength(2),
    );
    const fetchMock = globalThis.fetch as unknown as {
      mock: { calls: Array<[RequestInfo | URL]> };
    };
    const urls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(
      urls.some(
        (u) => u.includes('/reports/sales_report?date_from=2026-10-01') && !u.includes('date_to'),
      ),
    ).toBe(true);
  });

  it('offers employee and nozzle choices where the report supports them, "All" meaning no filter', async () => {
    await openAs(
      ['sale.view'],
      '/reports/attendant_nozzle_report',
      'Attendant & Nozzle Report',
      routes(),
    );
    const employee = await screen.findByLabelText('Employee');
    expect(within(employee).getByRole('option', { name: 'All employees' })).toBeInTheDocument();
    await userEvent.selectOptions(employee, 'e1');
    await userEvent.selectOptions(screen.getByLabelText('Nozzle'), 'n1');
    await userEvent.click(screen.getByRole('button', { name: /Refresh/ }));
    await waitFor(() => {
      const urls = (
        globalThis.fetch as unknown as { mock: { calls: Array<[RequestInfo | URL]> } }
      ).mock.calls.map((c) => String(c[0]));
      expect(urls.some((u) => u.includes('employee_id=e1') && u.includes('nozzle_id=n1'))).toBe(
        true,
      );
    });
  });

  it('hides the employee choice when the user may not see the roster', async () => {
    await openAs(
      ['sale.view'],
      '/reports/attendant_nozzle_report',
      'Attendant & Nozzle Report',
      routes({
        'GET /api/reports/filter-options': () =>
          json(200, { employees: [], nozzles: [{ label: 'N1', value: 'n1' }] }),
      }),
    );
    await screen.findByLabelText('Nozzle');
    expect(screen.queryByLabelText('Employee')).not.toBeInTheDocument();
  });

  it('print opens the preview with a fresh copy of the report; exports use the current filters', async () => {
    const preview = vi.fn(async () => ({ ok: true }));
    const save = vi.fn(async () => ({ ok: true, path: 'C:\\out\\sales_report.xlsx' }));
    window.pperp = {
      apiBase: '',
      launchSecret: 's',
      files: { pickPath: async () => null, save },
      print: { preview },
    } as never;
    await openAs(['sale.view'], '/reports/sales_report', 'Sales Report', routes());
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    const original = fetchMock.getMockImplementation() as unknown as (
      i: RequestInfo | URL,
      init?: RequestInit,
    ) => Promise<Response>;
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) =>
      String(input).includes('/export.xlsx')
        ? new Response(new Uint8Array([0x50, 0x4b]), { status: 200 })
        : original(input, init),
    );
    await screen.findByRole('table', { name: 'Sales Report' });
    await userEvent.type(screen.getByLabelText('To'), '2026-10-31');
    await userEvent.click(screen.getByRole('button', { name: 'Print' }));
    await waitFor(() => expect(preview).toHaveBeenCalledWith('<table>sales</table>', undefined));
    await userEvent.click(screen.getByRole('button', { name: 'Export Excel' }));
    await waitFor(() => expect(save).toHaveBeenCalledWith('sales_report.xlsx', btoa('PK')));
    const urls = fetchMock.mock.calls.map((c: unknown[]) => String(c[0]));
    expect(
      urls.some((u) => u.includes('/reports/sales_report/export.xlsx?date_to=2026-10-31')),
    ).toBe(true);
    expect(screen.getByRole('button', { name: 'Export CSV' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Export PDF' })).toBeInTheDocument();
  });

  it('shows the fuel type summary as cards', async () => {
    await openAs(['inventory.view'], '/reports/fuel_type_summary', 'Fuel Type Summary', {
      'GET /api/reports': () => json(200, hub()),
      'GET /api/reports/fuel_type_summary': () =>
        json(200, { ...sales, title: 'Fuel Type Summary' }),
      'GET /api/reports/fuel-type-summary/cards': () =>
        json(200, [
          {
            fuel_type: 'Petrol',
            tank_count: 2,
            total_capacity: '20000.000',
            total_current_stock: '4301.500',
            nozzle_count: 4,
            active_nozzle_count: 3,
            latest_variance_percent: '-0.40',
            latest_variance_classification: 'normal',
          },
        ]),
    });
    expect(await screen.findByText('Tanks: 2')).toBeInTheDocument();
    expect(screen.getByText('Total current stock: 4,301.500 L')).toBeInTheDocument();
    expect(screen.getByText('Nozzles: 3 active / 4 total')).toBeInTheDocument();
    expect(screen.getByText('Latest reconciliation variance: -0.40% (Normal)')).toBeInTheDocument();
  });

  it('an unavailable report explains itself', async () => {
    await openAs(['sale.view'], '/reports/cash_book', 'That report is not available to you.', {
      'GET /api/reports': () => json(200, hub()),
    });
  });
});

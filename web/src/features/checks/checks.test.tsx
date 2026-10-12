import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { json } from '@/test/mockApi';

const VIEW = ['check.view', 'check.explain'];

const result = (over: Record<string, unknown> = {}) => ({
  id: 'r1',
  key: 'tank.dip_matches_book',
  scope_type: 'tank',
  scope_id: 't1',
  business_date: '2026-10-12',
  area: 'Stock',
  sentence: 'MS-22: dip reading matches the book stock',
  expected: '2460.500',
  actual: '2000.000',
  difference: '-460.500',
  unit: 'litres',
  status: 'fail',
  links: [{ label: 'Open MS-22', route: '/tanks/t1' }],
  run_at: '2026-10-12T10:00:00Z',
  explanations: [],
  ...over,
});

const passing = result({
  id: 'r2',
  key: 'shift.litres_match_meters',
  sentence: 'Morning shift: litres billed equal litres through the meters (less testing)',
  expected: '40.000',
  actual: '40.000',
  difference: '0.000',
  status: 'pass',
  links: [{ label: 'Open Morning shift', route: '/shifts/s1' }],
});

const day = (results: unknown[]) => ({
  day: '2026-10-12',
  summary: {
    total: results.length,
    passed: results.filter((r) => (r as { status: string }).status === 'pass').length,
    warned: 0,
    failed: results.filter((r) => (r as { status: string }).status === 'fail').length,
  },
  results,
});

beforeEach(() => session.set(null));
afterEach(() => {
  vi.unstubAllGlobals();
  delete window.pperp;
});

describe('Checks screen', () => {
  it('lists the failing check first with both figures and a link to its source', async () => {
    await openAs(VIEW, '/checks', 'Checks', {
      'GET /api/checks': () => json(200, day([result(), passing])),
      'GET /api/tanks/t1': () =>
        json(404, { error: { code: 'not_found', message: 'x', details: {} } }),
    });
    expect(await screen.findByText('1 of 2 checks passed, 1 failed')).toBeInTheDocument();
    const rows = within(screen.getByRole('list', { name: 'Check results' })).getAllByRole(
      'listitem',
    );
    expect(
      within(rows[0]!).getByText('MS-22: dip reading matches the book stock'),
    ).toBeInTheDocument();
    expect(within(rows[0]!).getByText('Failed')).toBeInTheDocument();
    expect(within(rows[0]!).getByText('2,460.500 L')).toBeInTheDocument();
    expect(within(rows[0]!).getByText('2,000.000 L')).toBeInTheDocument();
    expect(within(rows[0]!).getByText('-460.500 L')).toBeInTheDocument();
    const link = within(rows[0]!).getByRole('link', { name: /Open MS-22/ });
    expect(link).toHaveAttribute('href', '/tanks/t1');
  });

  it('adds an explanation without changing the status shown', async () => {
    const withNote = result({
      explanations: [{ text: 'Dip stick was wet', by: 'owner1', at: '2026-10-12T11:00:00Z' }],
    });
    let saved = false;
    const api = await openAs(VIEW, '/checks', 'Checks', {
      'GET /api/checks': () => json(200, day([saved ? withNote : result()])),
      'POST /api/checks/r1/explanations': () => {
        saved = true;
        return json(201, withNote);
      },
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Add an explanation' }));
    const dialog = screen.getByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText('What explains this?'), 'Dip stick was wet');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save explanation' }));
    expect(await screen.findByText(/Dip stick was wet/)).toBeInTheDocument();
    expect(api.calls.some((c) => c.key === 'POST /api/checks/r1/explanations')).toBe(true);
    expect(screen.getByText('Failed')).toBeInTheDocument();
    expect(screen.getByText(/never changes the result/)).toBeInTheDocument();
  });

  it('offers no explanation button without the explain permission', async () => {
    await openAs(['check.view'], '/checks', 'Checks', {
      'GET /api/checks': () => json(200, day([result()])),
    });
    await screen.findByText('MS-22: dip reading matches the book stock');
    expect(screen.queryByRole('button', { name: 'Add an explanation' })).not.toBeInTheDocument();
  });

  it('says so when there is nothing to check yet', async () => {
    await openAs(VIEW, '/checks', 'Checks', { 'GET /api/checks': () => json(200, day([])) });
    expect(await screen.findByText('No checks for this day yet')).toBeInTheDocument();
  });
});

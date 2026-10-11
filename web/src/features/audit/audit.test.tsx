import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { json } from '@/test/mockApi';

const entry = (over: Record<string, unknown> = {}) => ({
  id: 'a1',
  created_at: '2026-10-11T09:15:30',
  event_type: 'settings_updated',
  actor: 'manager1',
  entity: 'AppSetting 123',
  description: 'company_name changed',
  ...over,
});
const base = {
  'GET /api/audit': () => json(200, [entry()]),
  'GET /api/audit/actors': () => json(200, [{ id: 'u1', username: 'manager1' }]),
};

beforeEach(() => session.set(null));
afterEach(() => vi.unstubAllGlobals());

describe('audit log', () => {
  it('shows entries with seconds, defaulting to the last 7 days', async () => {
    const api = await openAs(['audit.view'], '/audit', 'Audit Log', base);
    expect(await screen.findByRole('cell', { name: /:30$/ })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'company_name changed' })).toBeInTheDocument();
    const url = api.calls.find((c) => c.key === 'GET /api/audit')?.url ?? '';
    expect(url).toMatch(/date_from=\d{4}-\d{2}-\d{2}/);
    expect(url).toMatch(/date_to=\d{4}-\d{2}-\d{2}/);
  });

  it('applies filters only when Filter is pressed', async () => {
    const api = await openAs(['audit.view'], '/audit', 'Audit Log', base);
    await screen.findByRole('cell', { name: 'manager1' });
    await userEvent.type(screen.getByLabelText('Event contains'), 'settings');
    await userEvent.selectOptions(screen.getByLabelText('User'), 'u1');
    expect(api.calls.filter((c) => c.key === 'GET /api/audit')).toHaveLength(1);
    await userEvent.click(screen.getByRole('button', { name: 'Filter' }));
    await waitFor(() => {
      const last = api.calls.filter((c) => c.key === 'GET /api/audit').at(-1)?.url ?? '';
      expect(last).toContain('event_type=settings');
      expect(last).toContain('actor_id=u1');
    });
  });

  it('verifies the trail and reports tampering', async () => {
    await openAs(['audit.view'], '/audit', 'Audit Log', {
      ...base,
      'POST /api/audit/verify': () =>
        json(200, { intact: false, problems: ['entry 7 hash mismatch'] }),
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Verify Trail' }));
    const d = await screen.findByRole('dialog', { name: 'Audit trail has been altered' });
    expect(within(d).getByText('entry 7 hash mismatch')).toBeInTheDocument();
  });
});

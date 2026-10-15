import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { apiError, json } from '@/test/mockApi';

const rows = (over: Array<Record<string, unknown>> = []) => [
  { key: 'backup', name: 'Latest backup', state: 'good', detail: '3 hours ago (it should be under 36).', at: null },
  { key: 'integrity', name: 'Database integrity', state: 'good', detail: 'The database file is sound.', at: '2026-10-14T02:00:00Z' },
  { key: 'offsite', name: 'Copy off this PC', state: 'look', detail: 'No USB or network folder is set up for a second copy.', at: null },
  ...over,
];

beforeEach(() => session.set(null));
afterEach(() => vi.unstubAllGlobals());

describe('System health', () => {
  it('says each thing in words with Good / Look / Problem, and the worst one sets the headline', async () => {
    await openAs(['system_health.view'], '/system-health', 'System health', { 'GET /api/system/health': () => json(200, rows()) });
    const list = await screen.findByRole('list', { name: 'Checks' });
    expect(within(list).getAllByText('Good')).toHaveLength(2);
    expect(within(list).getByText('Look')).toBeInTheDocument();
    expect(screen.getByText('Some things need a look.')).toBeInTheDocument();
  });

  it('shows a problem in words and runs the checks on request', async () => {
    const api = await openAs(['system_health.view'], '/system-health', 'System health', {
      'GET /api/system/health': () => json(200, rows([{ key: 'disk', name: 'Free space', state: 'problem', detail: '1.2 GB free where the data lives.', at: null }])),
      'POST /api/system/health/run': () => json(200, rows()),
    });
    expect(await screen.findByText('Something needs fixing.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Run the checks now' }));
    await waitFor(() => expect(api.calls.some((c) => c.key === 'POST /api/system/health/run')).toBe(true));
  });

  it('sends the backup passphrase, never shows it back, and explains what losing it means', async () => {
    const api = await openAs(['system_health.view'], '/system-health', 'System health', {
      'GET /api/system/health': () => json(200, rows()),
      'PUT /api/system/backup-passphrase': (body) =>
        String((body as { passphrase: string }).passphrase).length < 10
          ? apiError(422, 'cannot_set_passphrase', 'Use a passphrase of at least 10 characters.')
          : { status: 204 },
    });
    expect(await screen.findByText(/without it those copies cannot be opened/)).toBeInTheDocument();
    const box = screen.getByLabelText(/Backup passphrase/);
    expect(box).toHaveAttribute('type', 'password');
    await userEvent.type(box, 'short');
    await userEvent.click(screen.getByRole('button', { name: 'Save passphrase' }));
    expect(await screen.findByText('Use a passphrase of at least 10 characters.')).toBeInTheDocument();
    await userEvent.clear(box);
    await userEvent.type(box, 'correct horse battery');
    await userEvent.click(screen.getByRole('button', { name: 'Save passphrase' }));
    await waitFor(() => expect(api.calls.filter((c) => c.key === 'PUT /api/system/backup-passphrase')).toHaveLength(2));
    await waitFor(() => expect(screen.getByLabelText(/Backup passphrase/)).toHaveValue(''));
  });
});

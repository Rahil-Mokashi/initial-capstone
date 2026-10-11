import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { apiError, json } from '@/test/mockApi';
import { formatSize, offsiteMessage } from './BackupsPage';

const ADMIN = ['backup.manage'];
const backup = (over: Record<string, unknown> = {}) => ({
  filename: 'backup_20261011_manual.db',
  size_bytes: 2048,
  created_at: '2026-10-11T09:00:00',
  ...over,
});
const listing = (over: Record<string, unknown> = {}) => ({
  backups: [backup()],
  offsite: { state: 'ok', destination: 'E:\\', age_days: 1, stale_after_days: 7 },
  configured_offsite_dir: 'E:\\',
  ...over,
});

beforeEach(() => session.set(null));
afterEach(() => vi.unstubAllGlobals());

describe('backups', () => {
  it('formats sizes like the Qt screen and words each offsite state', () => {
    expect(formatSize(512)).toBe('512.0 B');
    expect(formatSize(2048)).toBe('2.0 KB');
    expect(formatSize(5 * 1024 * 1024)).toBe('5.0 MB');
    expect(offsiteMessage({ state: 'ok', stale_after_days: 7 })).toBeNull();
    expect(offsiteMessage({ state: 'never', stale_after_days: 7 })).toMatch(/No off-device backup/);
    expect(
      offsiteMessage({ state: 'unreachable', destination: 'E:\\', stale_after_days: 7 }),
    ).toMatch(/not reachable/);
    expect(offsiteMessage({ state: 'stale', age_days: 9.2, stale_after_days: 7 })).toMatch(
      /9 days old/,
    );
  });

  it('lists backups, shows the stale warning, and backs up now', async () => {
    const api = await openAs(ADMIN, '/backups', 'Backups', {
      'GET /api/backups': () =>
        json(
          200,
          listing({
            offsite: { state: 'stale', destination: 'E:\\', age_days: 12, stale_after_days: 7 },
          }),
        ),
      'POST /api/backups': () => json(201, backup({ filename: 'new.db' })),
    });
    expect(
      await screen.findByRole('cell', { name: 'backup_20261011_manual.db' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '2.0 KB' })).toBeInTheDocument();
    expect(screen.getByText(/12 days old/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Back Up Now' }));
    await waitFor(() => expect(api.calls.some((c) => c.key === 'POST /api/backups')).toBe(true));
    expect(await screen.findByText('Backup created: new.db')).toBeInTheDocument();
  });

  it('reports an integrity problem list', async () => {
    await openAs(ADMIN, '/backups', 'Backups', {
      'GET /api/backups': () => json(200, listing()),
      'POST /api/backups/check': () => json(200, { ok: false, messages: ['row 5 missing'] }),
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Check Integrity' }));
    const d = await screen.findByRole('dialog', { name: 'Database has problems' });
    expect(within(d).getByText('row 5 missing')).toBeInTheDocument();
  });

  it('restores only after a strong confirmation, then a reason, and says to restart', async () => {
    const api = await openAs(ADMIN, '/backups', 'Backups', {
      'GET /api/backups': () => json(200, listing()),
      'POST /api/backups/backup_20261011_manual.db/restore': () => ({ status: 204 }),
    });
    await userEvent.click(await screen.findByRole('button', { name: /Restore backup_2026/ }));
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }),
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(api.calls.some((c) => c.key.includes('/restore'))).toBe(false);

    await userEvent.click(screen.getByRole('button', { name: /Restore backup_2026/ }));
    expect(screen.getByRole('dialog')).toHaveTextContent('replaces ALL current data');
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Continue' }),
    );
    await userEvent.type(await screen.findByLabelText(/Reason for restoring/), 'wrong data');
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Restore' }),
    );
    expect(await screen.findByText(/Close the application and open it again/)).toBeInTheDocument();
    expect(api.calls.find((c) => c.key.includes('/restore'))?.body).toEqual({
      reason: 'wrong data',
    });
  });

  it('copies to the configured folder and shows a refusal inside the dialog', async () => {
    const api = await openAs(ADMIN, '/backups', 'Backups', {
      'GET /api/backups': () => json(200, listing()),
      'POST /api/backups/backup_20261011_manual.db/copy': () =>
        apiError(409, 'conflict', 'The folder is not writable.'),
    });
    await userEvent.click(await screen.findByRole('button', { name: /Copy backup_2026/ }));
    const d = screen.getByRole('dialog');
    expect(within(d).getByLabelText('Destination folder')).toHaveValue('E:\\');
    await userEvent.click(within(d).getByRole('button', { name: 'Copy' }));
    expect(await within(d).findByRole('alert')).toHaveTextContent('not writable');
    expect(api.calls.find((c) => c.key.includes('/copy'))?.body).toEqual({
      destination_dir: 'E:\\',
    });
  });
});

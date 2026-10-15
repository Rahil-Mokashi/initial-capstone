import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { apiError, json } from '@/test/mockApi';

const setting = (key: string, value: string) => ({ key, value, default: value, label: key, help: '', question_id: 'L', choices: null });
const SETTINGS = [
  setting('mail_enabled', 'off'),
  setting('mail_host', ''),
  setting('mail_port', '587'),
  setting('mail_security', 'starttls'),
  setting('mail_user', ''),
  setting('mail_from', ''),
  setting('mail_to', ''),
  setting('mail_send_hour', '21'),
];
const status = (over: Record<string, unknown> = {}) => ({ enabled: false, problems: [], password_set: false, pending: 0, last_sent: null, outbox: [], ...over });

beforeEach(() => session.set(null));
afterEach(() => vi.unstubAllGlobals());

describe('Email summary', () => {
  it('starts off, says it sends figures only, and what is missing once it is turned on', async () => {
    await openAs(['mail.manage'], '/mail', 'Email summary', {
      'GET /api/pump-settings': () => json(200, SETTINGS),
      'GET /api/mail': () => json(200, status({ enabled: true, problems: ['Fill in the mail server.'] })),
    });
    expect(await screen.findByText(/figures only, no names/)).toBeInTheDocument();
    expect(screen.getByText('Not ready')).toBeInTheDocument();
    expect(screen.getByText('Fill in the mail server.')).toBeInTheDocument();
    expect(screen.getByLabelText('Mail password')).toHaveAttribute('type', 'password');
  });

  it('saves only what changed, sends the password separately, and never shows it again', async () => {
    const api = await openAs(['mail.manage'], '/mail', 'Email summary', {
      'GET /api/pump-settings': () => json(200, SETTINGS),
      'GET /api/mail': () => json(200, status()),
      'PUT /api/pump-settings/mail_enabled': () => json(200, setting('mail_enabled', 'on')),
      'PUT /api/pump-settings/mail_host': () => json(200, setting('mail_host', 'smtp.example.com')),
      'PUT /api/mail/password': () => ({ status: 204 }),
    });
    await userEvent.selectOptions(await screen.findByLabelText('Send the daily summary'), 'on');
    await userEvent.type(screen.getByLabelText('Mail server'), 'smtp.example.com');
    await userEvent.type(screen.getByLabelText('Mail password'), 'hunter2-hunter2');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(api.calls.some((c) => c.key === 'PUT /api/mail/password')).toBe(true));
    expect(api.calls.filter((c) => c.key.startsWith('PUT /api/pump-settings/')).map((c) => c.key).sort()).toEqual([
      'PUT /api/pump-settings/mail_enabled',
      'PUT /api/pump-settings/mail_host',
    ]);
    expect(api.calls.find((c) => c.key === 'PUT /api/mail/password')!.body).toEqual({ password: 'hunter2-hunter2' });
    await waitFor(() => expect(screen.getByLabelText('Mail password')).toHaveValue(''));
  });

  it('shows why a test message failed, in the mail servers own words', async () => {
    await openAs(['mail.manage'], '/mail', 'Email summary', {
      'GET /api/pump-settings': () => json(200, SETTINGS),
      'GET /api/mail': () => json(200, status({ enabled: true })),
      'POST /api/mail/test': () => apiError(422, 'mail_not_ready', 'The mail server did not accept the message: SMTPAuthenticationError: 535 nope'),
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Send a test message' }));
    expect(await screen.findByText(/did not accept the message/)).toBeInTheDocument();
  });

  it('lists recent messages with their state', async () => {
    await openAs(['mail.manage'], '/mail', 'Email summary', {
      'GET /api/pump-settings': () => json(200, SETTINGS),
      'GET /api/mail': () =>
        json(200, status({ enabled: true, outbox: [{ day: '2026-10-13', subject: 'Pump summary 13 Oct: 80000.00 sold', status: 'gave_up', attempts: 6, last_error: 'ConnectionRefusedError', sent_at: null }] })),
    });
    expect(await screen.findByText('Gave up')).toBeInTheDocument();
    expect(screen.getByText('ConnectionRefusedError')).toBeInTheDocument();
  });
});

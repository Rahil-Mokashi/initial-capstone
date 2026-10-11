import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { apiError, json } from '@/test/mockApi';

const profile = (over: Record<string, unknown> = {}) => ({
  company_name: null,
  address_line1: null,
  address_line2: null,
  city: null,
  state: null,
  postal_code: null,
  phone: null,
  email: null,
  gst_number: null,
  licence_number: null,
  receipt_footer: null,
  offsite_backup_dir: null,
  has_company_profile: false,
  ...over,
});

beforeEach(() => session.set(null));
afterEach(() => {
  vi.unstubAllGlobals();
  window.pperp = undefined;
});

describe('company profile', () => {
  it('warns when no business name is set and saves what was typed', async () => {
    const api = await openAs(['settings.view', 'settings.manage'], '/settings', 'Company Profile', {
      'GET /api/settings': () => json(200, profile()),
      'PUT /api/settings': () =>
        json(200, profile({ company_name: 'Sai Fuels', has_company_profile: true })),
    });
    expect(await screen.findByText(/No business name is set/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Business name/), 'Sai Fuels');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.key === 'PUT /api/settings')?.body).toMatchObject({
        company_name: 'Sai Fuels',
        gst_number: '',
      }),
    );
    expect(await screen.findByText('Company profile saved.')).toBeInTheDocument();
  });

  it('puts the server message next to the GST box, and Discard changes reloads the saved values', async () => {
    await openAs(['settings.view', 'settings.manage'], '/settings', 'Company Profile', {
      'GET /api/settings': () =>
        json(200, profile({ company_name: 'Sai Fuels', has_company_profile: true })),
      'PUT /api/settings': () =>
        apiError(422, 'validation_error', 'Please check the form.', {
          fields: [{ field: 'gst_number', message: 'A GST number is 15 alphanumeric characters' }],
        }),
    });
    expect(screen.queryByText(/No business name is set/)).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/GST number/), 'BAD');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText(/15 alphanumeric characters/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Discard changes' }));
    expect(screen.getByLabelText(/GST number/)).toHaveValue('');
    expect(screen.getByLabelText(/Business name/)).toHaveValue('Sai Fuels');
  });

  it('is read-only without settings.manage', async () => {
    await openAs(['settings.view'], '/settings', 'Company Profile', {
      'GET /api/settings': () => json(200, profile()),
    });
    expect(screen.getByLabelText(/Business name/)).toHaveAttribute('readonly');
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
  });

  it('fills the folder box from the folder picker', async () => {
    window.pperp = {
      apiBase: '',
      launchSecret: 's',
      files: { pickPath: async () => null, pickFolder: async () => 'E:\\Backups' },
    } as never;
    await openAs(['settings.view', 'settings.manage'], '/settings', 'Company Profile', {
      'GET /api/settings': () => json(200, profile()),
    });
    await userEvent.click(screen.getByRole('button', { name: 'Browse...' }));
    expect(screen.getByLabelText(/Off-device backup folder/)).toHaveValue('E:\\Backups');
  });
});

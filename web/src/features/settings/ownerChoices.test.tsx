import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '@/api/session';
import { openAs } from '@/test/harness';
import { json } from '@/test/mockApi';

beforeEach(() => session.set(null));
afterEach(() => vi.unstubAllGlobals());

const setting = (over: Record<string, unknown>) => ({
  key: 'credit_over_limit',
  value: 'warn',
  default: 'warn',
  label: 'Credit over the limit',
  help: 'warn: allow with a recorded owner override. block: refuse.',
  question_id: 'V-14',
  choices: ['warn', 'block'],
  ...over,
});

describe('Owner Choices', () => {
  it('lists each decision with its question ID and standard answer, and saves a change', async () => {
    const api = await openAs(
      ['settings.view', 'owner_choice.manage'],
      '/owner-choices',
      'Owner Choices',
      {
        'GET /api/pump-settings': () =>
          json(200, [
            setting({}),
            setting({
              key: 'dip_tolerance_percent',
              value: '0.5',
              default: '0.5',
              label: 'Dip difference tolerance (%)',
              question_id: 'T-02',
              choices: null,
            }),
          ]),
        'PUT /api/pump-settings/credit_over_limit': () => json(200, setting({ value: 'block' })),
      },
    );
    const form = await screen.findByRole('form', { name: 'Credit over the limit' });
    expect(within(form).getByText(/Question V-14/)).toBeInTheDocument();
    expect(screen.getByRole('form', { name: 'Dip difference tolerance (%)' })).toBeInTheDocument();
    expect(within(form).getByRole('button', { name: 'Save' })).toBeDisabled(); // nothing changed yet
    await userEvent.selectOptions(within(form).getByLabelText('Credit over the limit'), 'block');
    expect(within(form).getByText(/Standard: Warn/)).toBeInTheDocument();
    await userEvent.click(within(form).getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(api.calls.some((c) => c.key === 'PUT /api/pump-settings/credit_over_limit')).toBe(
        true,
      ),
    );
    expect(
      api.calls.find((c) => c.key === 'PUT /api/pump-settings/credit_over_limit')!.body,
    ).toEqual({ value: 'block' });
  });
});

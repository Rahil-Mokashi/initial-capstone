import { describe, expect, it } from 'vitest';
import { SHIFT_ENTRY_STEPS, todayPlan } from './plan';

describe('today plan', () => {
  it('gives the owner checks, day status and credit, and the overview', () => {
    expect(todayPlan('OWNER')).toEqual({
      focus: ['digest', 'review', 'checks', 'day_status', 'credit_outstanding', 'credit_chase', 'payroll'],
      overview: true,
    });
    expect(todayPlan('ADMIN').focus).toContain('checks');
  });

  it('gives the cashier only the shift entry list, with no overview', () => {
    expect(todayPlan('DATA_ENTRY')).toEqual({ focus: ['shift_entry'], overview: false });
  });

  it('gives the manager shift close and checks; attendants never sign in, so they have no list', () => {
    expect(todayPlan('MANAGER').focus).toEqual(['manager_close', 'checks']);
    expect(todayPlan('ATTENDANT')).toEqual({ focus: [], overview: true });
  });

  it('falls back to the plain dashboard for an unknown role', () => {
    expect(todayPlan('SOMETHING_NEW')).toEqual({ focus: [], overview: true });
    expect(todayPlan(null).overview).toBe(true);
  });

  it('uses the staff words and every step points at a real screen', () => {
    const text = SHIFT_ENTRY_STEPS.map((s) => `${s.label} ${s.hint}`).join(' ');
    for (const word of ['DTP Card', 'PTM', 'Advance', 'Final', 'Bouser'])
      expect(text).toContain(word);
    expect(SHIFT_ENTRY_STEPS.every((s) => s.to.startsWith('/'))).toBe(true);
  });
});

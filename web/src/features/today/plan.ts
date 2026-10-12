// What each role lands on. Pure data so it can be tested and changed in one place.
// V-01 / V-02 (open): the order of the data-entry steps follows how the paper bundle usually arrives.

export type FocusId =
  'checks' | 'day_status' | 'credit_outstanding' | 'shift_entry' | 'manager_close' | 'my_shift';

export interface TodayPlan {
  focus: FocusId[];
  /** Also show the full dashboard (sales trend, tank gauges, roster) under the short list. */
  overview: boolean;
}

export function todayPlan(role: string | null | undefined): TodayPlan {
  switch (role) {
    case 'OWNER':
    case 'ADMIN':
      return { focus: ['checks', 'day_status', 'credit_outstanding'], overview: true };
    case 'MANAGER':
      return { focus: ['manager_close', 'checks'], overview: true };
    case 'ACCOUNTANT':
      return { focus: ['checks', 'credit_outstanding'], overview: true };
    case 'DATA_ENTRY':
      return { focus: ['shift_entry'], overview: false };
    case 'SHIFT_SUPERVISOR':
      return { focus: ['manager_close'], overview: false };
    case 'ATTENDANT':
      return { focus: ['my_shift'], overview: false };
    default:
      return { focus: [], overview: true };
  }
}

export interface EntryStep {
  label: string;
  hint: string;
  to: string;
  permission: string;
}

/** The shift bundle in the order it arrives, in the staff's own words. Only screens that exist are linked. */
export const SHIFT_ENTRY_STEPS: EntryStep[] = [
  {
    label: 'Nozzle readings',
    hint: 'Closing meter for MS and HSD nozzles, testing litres',
    to: '/shifts',
    permission: 'shift.manage',
  },
  {
    label: 'Credit bills',
    hint: 'Bill no., name, amount (including Stock Transfer to Bouser)',
    to: '/terminal',
    permission: 'sale.manage',
  },
  {
    label: 'Card, DTP Card, Phone Pay, PTM',
    hint: 'Totals per payment mode for the shift',
    to: '/shift-totals',
    permission: 'reconciliation.manage',
  },
  {
    label: 'Expenses',
    hint: 'Tea, trips, repairs, diesel for own vehicles, cash short',
    to: '/expenses',
    permission: 'expense.manage',
  },
  {
    label: 'Oil sales',
    hint: 'HP Racer, Milcy Turbo: stock in, sold per shift',
    to: '/lubricants',
    permission: 'lubricant.manage',
  },
  {
    label: 'Bouser',
    hint: 'Stock Transfer, delivery bills with transport, bowser meter',
    to: '/bowser',
    permission: 'bowser.manage',
  },
  {
    label: 'Advance, Final and bank deposits',
    hint: 'Cash handed over, and each deposit with its bank',
    to: '/reconciliation',
    permission: 'reconciliation.manage',
  },
];

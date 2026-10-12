import { describe, expect, it } from 'vitest';
import { alertRoute } from './alertRoutes';

describe('alertRoute', () => {
  it('sends each alert to the screen it is about', () => {
    expect(alertRoute('low_fuel', 'MS-16 is low on fuel')).toBe('/tanks');
    expect(alertRoute('cash_shortage', 'x')).toBe('/reconciliation');
    expect(alertRoute('outstanding_credit', 'x')).toBe('/credit');
    expect(alertRoute('supplier_payment_due', 'x')).toBe('/procurement?tab=orders');
    expect(alertRoute('database_error', 'x')).toBe('/audit');
    expect(alertRoute('backup_failure', 'x')).toBe('/backups');
  });
  it('resolves "pending approval" from the title', () => {
    expect(alertRoute('pending_approval', '3 expenses waiting')).toBe('/expenses');
    expect(alertRoute('pending_approval', 'Reconciliation waiting')).toBe('/reconciliation');
  });
  it('returns null for a category it does not know', () => {
    expect(alertRoute('something_new', 'x')).toBeNull();
  });
});

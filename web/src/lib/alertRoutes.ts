// Where clicking an alert takes you: the screen the alert is about (the Qt shell's _NOTIFICATION_TARGETS).
// A screen, deliberately, not a row inside it.
const TARGETS: Record<string, string> = {
  low_fuel: '/tanks',
  fuel_variance: '/tanks',
  cash_shortage: '/reconciliation',
  cash_excess: '/reconciliation',
  payment_mismatch: '/reconciliation',
  failed_reconciliation: '/reconciliation',
  attendance_issue: '/attendance',
  outstanding_credit: '/credit',
  supplier_payment_due: '/procurement?tab=orders',
  unauthorized_action: '/audit',
  database_error: '/audit',
  backup_failure: '/backups',
};

export function alertRoute(category: string, title: string): string | null {
  // "Pending approval" covers two screens; the alert's own title says which.
  if (category === 'pending_approval') {
    return /expense/i.test(title) ? '/expenses' : '/reconciliation';
  }
  return TARGETS[category] ?? null;
}

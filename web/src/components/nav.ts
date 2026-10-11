// Navigation mirrors the Qt app's groups (app/ui/main_window.py `_card_groups`)
// and each item's permission. Only screens with a `to` are migrated so far;
// the rest are listed (so the structure is familiar) but marked "soon".
export interface NavItem {
  label: string;
  permission: string;
  /** Route, when the screen exists in the new UI. */
  to?: string;
}
export interface NavGroup {
  label: string;
  items: NavItem[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Masters',
    items: [
      { label: 'Employees', permission: 'employee.view', to: '/employees' },
      { label: 'Users', permission: 'user.manage', to: '/users' },
      { label: 'Fuel Prices', permission: 'fuel_price.view', to: '/fuel-prices' },
      { label: 'Tanks', permission: 'inventory.view', to: '/tanks' },
      { label: 'Nozzles & Dispensers', permission: 'nozzle.view' },
      { label: 'Suppliers', permission: 'procurement.view' },
      { label: 'Company Profile', permission: 'settings.view' },
    ],
  },
  {
    label: 'Operations',
    items: [
      { label: 'Terminal', permission: 'sale.manage' },
      { label: 'Sales', permission: 'sale.view' },
      { label: 'Shifts', permission: 'shift.view' },
      { label: 'My Shift', permission: 'my_assignment.view' },
      { label: 'Attendance', permission: 'attendance.view' },
      { label: 'Leave', permission: 'leave.view' },
      { label: 'Credit', permission: 'credit.view' },
      { label: 'Expenses', permission: 'expense.view' },
      { label: 'Reconciliation', permission: 'reconciliation.view' },
      { label: 'Procurement', permission: 'procurement.view' },
    ],
  },
  {
    label: 'Settings',
    items: [
      { label: 'Backups', permission: 'backup.manage' },
      { label: 'Audit Log', permission: 'audit.view' },
    ],
  },
];

/** Groups with only the items this user may see; empty groups disappear (as in Qt). */
export function visibleGroups(can: (permission: string) => boolean): NavGroup[] {
  return NAV_GROUPS.map((g) => ({ ...g, items: g.items.filter((i) => can(i.permission)) })).filter(
    (g) => g.items.length > 0,
  );
}

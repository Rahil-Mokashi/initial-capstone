// Navigation mirrors the Qt app's groups (app/ui/main_window.py `_card_groups`)
// and each item's permission. Only screens with a `to` are migrated so far;
// the rest are listed (so the structure is familiar) but marked "soon".
export interface NavItem {
  label: string;
  /** One permission, or a list where holding ANY of them is enough (the Reports entry). */
  permission: string | string[];
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
      { label: 'Nozzles & Dispensers', permission: 'nozzle.view', to: '/nozzles' },
      { label: 'Suppliers', permission: 'procurement.view', to: '/procurement?tab=suppliers' },
      { label: 'Company Profile', permission: 'settings.view' },
    ],
  },
  {
    label: 'Operations',
    items: [
      { label: 'Terminal', permission: 'sale.manage', to: '/terminal' },
      { label: 'Sales', permission: 'sale.view', to: '/sales' },
      { label: 'Shifts', permission: 'shift.view', to: '/shifts' },
      { label: 'My Shift', permission: 'my_assignment.view', to: '/my-shift' },
      { label: 'Attendance', permission: 'attendance.view', to: '/attendance' },
      { label: 'Leave', permission: 'leave.view', to: '/leave' },
      { label: 'Credit', permission: 'credit.view', to: '/credit' },
      { label: 'Expenses', permission: 'expense.view', to: '/expenses' },
      { label: 'Reconciliation', permission: 'reconciliation.view', to: '/reconciliation' },
      { label: 'Procurement', permission: 'procurement.view', to: '/procurement?tab=orders' },
    ],
  },
  {
    label: 'Reports',
    items: [
      {
        label: 'Reports',
        permission: [
          'inventory.view',
          'sale.view',
          'expense.view',
          'credit.view',
          'reconciliation.view',
          'analytics.view',
        ],
        to: '/reports',
      },
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
  return NAV_GROUPS.map((g) => ({
    ...g,
    items: g.items.filter((i) =>
      Array.isArray(i.permission) ? i.permission.some(can) : can(i.permission),
    ),
  })).filter((g) => g.items.length > 0);
}

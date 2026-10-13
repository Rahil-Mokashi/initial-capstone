// Navigation mirrors the Qt app's groups (app/ui/main_window.py `_card_groups`)
// and each item's permission. Only screens with a `to` are migrated so far;
// the rest are listed (so the structure is familiar) but marked "soon".
export interface NavItem {
  label: string;
  /** One permission, or a list where holding ANY of them is enough (the Reports entry). */
  permission: string | string[];
  /** Route, when the screen exists in the new UI. */
  to?: string;
  /** Roles that hold the permission (for dropdowns) but should not see this in their short menu. */
  hideFor?: string[];
}
export interface NavGroup {
  label: string;
  items: NavItem[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Masters',
    items: [
      {
        label: 'Employees',
        permission: 'employee.view',
        to: '/employees',
        hideFor: ['DATA_ENTRY'],
      },
      { label: 'Users', permission: 'user.manage', to: '/users' },
      {
        label: 'Fuel Prices',
        permission: 'fuel_price.view',
        to: '/fuel-prices',
        hideFor: ['DATA_ENTRY'],
      },
      { label: 'Tanks', permission: 'inventory.view', to: '/tanks' },
      {
        label: 'Nozzles & Dispensers',
        permission: 'nozzle.view',
        to: '/nozzles',
        hideFor: ['DATA_ENTRY'],
      },
      { label: 'Suppliers', permission: 'procurement.view', to: '/procurement?tab=suppliers' },
      {
        label: 'Company Profile',
        permission: 'settings.view',
        to: '/settings',
        hideFor: ['DATA_ENTRY'],
      },
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
      { label: 'Checks', permission: 'check.view', to: '/checks' },
      { label: 'Review', permission: 'entry.view', to: '/review', hideFor: ['DATA_ENTRY'] },
      { label: 'Bank Matching', permission: 'bank_recon.view', to: '/bank' },
      { label: 'Payroll', permission: 'payroll.view', to: '/payroll' },
      { label: 'Credit', permission: 'credit.view', to: '/credit' },
      {
        label: 'Credit Ageing',
        permission: 'credit.view',
        to: '/credit/ageing',
        hideFor: ['DATA_ENTRY'],
      },
      { label: 'Close Shift', permission: 'shift.manage', to: '/close-shift' },
      {
        label: 'Card / Phone Pay totals',
        permission: 'reconciliation.manage',
        to: '/shift-totals',
        hideFor: ['DATA_ENTRY'],
      },
      { label: 'Expenses', permission: 'expense.view', to: '/expenses' },
      { label: 'Oil / Lubricants', permission: 'lubricant.view', to: '/lubricants' },
      { label: 'Bowser Van', permission: 'bowser.view', to: '/bowser' },
      { label: 'Reconciliation', permission: 'reconciliation.view', to: '/reconciliation' },
      { label: 'Procurement', permission: 'procurement.view', to: '/procurement?tab=orders' },
    ],
  },
  {
    label: 'Reports',
    items: [
      { label: 'Daily Report', permission: 'daily_report.view', to: '/daily-report' },
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
        hideFor: ['DATA_ENTRY'],
      },
    ],
  },
  {
    label: 'Settings',
    items: [
      { label: 'Owner Choices', permission: 'owner_choice.manage', to: '/owner-choices' },
      { label: 'Backups', permission: 'backup.manage', to: '/backups' },
      { label: 'Devices', permission: 'device.manage', to: '/devices' },
      { label: 'Audit Log', permission: 'audit.view', to: '/audit' },
    ],
  },
];

/** Groups with only the items this user may see; empty groups disappear (as in Qt). */
export function visibleGroups(
  can: (permission: string) => boolean,
  role?: string | null,
): NavGroup[] {
  return NAV_GROUPS.map((g) => ({
    ...g,
    items: g.items.filter(
      (i) =>
        (Array.isArray(i.permission) ? i.permission.some(can) : can(i.permission)) &&
        !(role && i.hideFor?.includes(role)),
    ),
  })).filter((g) => g.items.length > 0);
}

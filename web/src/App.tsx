import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { useAuth } from '@/auth/AuthContext';
import { AppShell } from '@/components/AppShell';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { ChangePasswordPage } from '@/features/auth/ChangePasswordPage';
import { LoginPage } from '@/features/auth/LoginPage';
import { EmployeeDetailPage } from '@/features/employees/EmployeeDetailPage';
import { EmployeesPage } from '@/features/employees/EmployeesPage';
import { AuditPage } from '@/features/audit/AuditPage';
import { BackupsPage } from '@/features/backups/BackupsPage';
import { SettingsPage } from '@/features/settings/SettingsPage';
import { FuelPricesPage } from '@/features/fuel-prices/FuelPricesPage';
import { UsersPage } from '@/features/users/UsersPage';
import { UserDetailPage } from '@/features/users/UserDetailPage';
import { NozzlesPage } from '@/features/nozzles/NozzlesPage';
import { ProcurementPage } from '@/features/procurement/ProcurementPage';
import {
  DeliveryDetailPage,
  InvoiceDetailPage,
  OrderDetailPage,
} from '@/features/procurement/DetailPages';
import { ShiftsPage } from '@/features/shifts/ShiftsPages';
import { ShiftDetailPage } from '@/features/shifts/ShiftsPages';
import { MyShiftPage } from '@/features/shifts/ShiftsPages';
import { AttendancePage } from '@/features/attendance/AttendancePage';
import { LeavePage } from '@/features/attendance/LeavePage';
import { SalesPage } from '@/features/sales/SalesPage';
import { TerminalPage } from '@/features/terminal/TerminalPage';
import { ChecksPage } from '@/features/checks/ChecksPage';
import { CreditPage } from '@/features/credit/CreditPage';
import { ExpensesPage } from '@/features/expenses/ExpensesPage';
import { ReconciliationPage } from '@/features/reconciliation/ReconciliationPage';
import { ReportPage, ReportsHubPage } from '@/features/reports/ReportsPages';
import { AnalyticsPage } from '@/features/analytics/AnalyticsPage';
import { AlertsPage } from '@/features/alerts/alerts';
import { DashboardPage } from '@/features/dashboard/DashboardPage';
import { SupportPage } from '@/features/support/SupportPage';
import { TankDetailPage } from '@/features/tanks/TankDetailPage';
import { TanksPage } from '@/features/tanks/TanksPage';

/** Redirects to login when signed out (UX only - the server enforces auth on every call). */
function RequireAuth() {
  const { user } = useAuth();
  const location = useLocation();
  if (!user)
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  if (user.must_change_password) return <ChangePasswordPage />;
  return <Outlet />;
}

export function App() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth />}>
          <Route element={<AppShell />}>
            {/* One route per screen: opening Tanks again re-uses this page, it can never stack a second copy. */}
            <Route path="/users" element={<UsersPage />} />
            <Route path="/users/:id" element={<UserDetailPage />} />
            <Route path="/nozzles" element={<NozzlesPage />} />
            <Route path="/procurement" element={<ProcurementPage />} />
            <Route path="/procurement/orders/:id" element={<OrderDetailPage />} />
            <Route path="/procurement/deliveries/:id" element={<DeliveryDetailPage />} />
            <Route path="/procurement/invoices/:id" element={<InvoiceDetailPage />} />
            <Route path="/shifts" element={<ShiftsPage />} />
            <Route path="/shifts/:id" element={<ShiftDetailPage />} />
            <Route path="/my-shift" element={<MyShiftPage />} />
            <Route path="/attendance" element={<AttendancePage />} />
            <Route path="/leave" element={<LeavePage />} />
            <Route path="/sales" element={<SalesPage />} />
            <Route path="/terminal" element={<TerminalPage />} />
            <Route path="/checks" element={<ChecksPage />} />
            <Route path="/credit" element={<CreditPage />} />
            <Route path="/expenses" element={<ExpensesPage />} />
            <Route path="/reconciliation" element={<ReconciliationPage />} />
            <Route path="/reports" element={<ReportsHubPage />} />
            <Route path="/reports/:key" element={<ReportPage />} />
            <Route path="/analytics" element={<AnalyticsPage />} />
            <Route path="/" element={<DashboardPage />} />
            <Route path="/alerts" element={<AlertsPage />} />
            <Route path="/support" element={<SupportPage />} />
            <Route path="/tanks" element={<TanksPage />} />
            <Route path="/tanks/:id" element={<TankDetailPage />} />
            <Route path="/fuel-prices" element={<FuelPricesPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/backups" element={<BackupsPage />} />
            <Route path="/audit" element={<AuditPage />} />
            <Route path="/employees" element={<EmployeesPage />} />
            <Route path="/employees/:id" element={<EmployeeDetailPage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ErrorBoundary>
  );
}

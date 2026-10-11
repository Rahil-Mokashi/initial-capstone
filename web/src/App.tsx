import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { useAuth } from '@/auth/AuthContext';
import { AppShell } from '@/components/AppShell';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { ChangePasswordPage } from '@/features/auth/ChangePasswordPage';
import { LoginPage } from '@/features/auth/LoginPage';
import { EmployeeDetailPage } from '@/features/employees/EmployeeDetailPage';
import { EmployeesPage } from '@/features/employees/EmployeesPage';
import { TankDetailPage } from '@/features/tanks/TankDetailPage';
import { TanksPage } from '@/features/tanks/TanksPage';

/** Redirects to login when signed out (UX only - the server enforces auth on every call). */
function RequireAuth() {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
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
            <Route path="/tanks" element={<TanksPage />} />
            <Route path="/tanks/:id" element={<TankDetailPage />} />
            <Route path="/employees" element={<EmployeesPage />} />
            <Route path="/employees/:id" element={<EmployeeDetailPage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/tanks" replace />} />
      </Routes>
    </ErrorBoundary>
  );
}

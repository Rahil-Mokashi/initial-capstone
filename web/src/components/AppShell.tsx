import { Fuel, LogOut, Moon, Sun } from 'lucide-react';
import { useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '@/auth/AuthContext';
import { cn } from '@/lib/cn';
import { visibleGroups } from './nav';
import { Button } from './ui/Button';

type Theme = 'system' | 'light' | 'dark';

function applyTheme(theme: Theme) {
  if (theme === 'system') document.documentElement.removeAttribute('data-theme');
  else document.documentElement.setAttribute('data-theme', theme);
}

function Sidebar() {
  const { can } = useAuth();
  const groups = visibleGroups(can);
  const location = useLocation();
  return (
    <aside className="flex w-[var(--sidebar-w)] shrink-0 flex-col bg-ink text-ink-fg">
      <div className="flex items-center gap-3 border-b border-ink-2 px-5 py-5">
        <span className="flex size-10 items-center justify-center rounded-md bg-primary text-primary-fg">
          <Fuel className="size-5" aria-hidden />
        </span>
        <div className="leading-tight">
          <p className="text-base font-bold">Petrol Pump ERP</p>
          <p className="text-xs text-ink-muted">Back office</p>
        </div>
      </div>
      <nav
        aria-label="Main"
        className="flex-1 overflow-y-auto px-3 py-4 [scrollbar-color:var(--ink-muted)_transparent] [scrollbar-width:thin]"
      >
        {groups.map((group) => (
          <div key={group.label} className="mb-5">
            <p className="px-3 pb-1.5 text-xs font-bold tracking-widest text-ink-muted uppercase">
              {group.label}
            </p>
            <ul className="flex flex-col gap-0.5">
              {group.items.map((item) => (
                <li key={item.label}>
                  {item.to ? (
                    <NavLink
                      to={item.to}
                      className={({ isActive }) =>
                        cn(
                          'flex min-h-[44px] items-center rounded-md px-3 text-sm font-medium',
                          // Two entries can open one screen on different tabs (?tab=...); then the tab decides.
                          (
                            item.to?.includes('?')
                              ? item.to === location.pathname + location.search
                              : isActive
                          )
                            ? 'bg-primary text-primary-fg'
                            : 'text-ink-fg hover:bg-ink-2',
                        )
                      }
                    >
                      {item.label}
                    </NavLink>
                  ) : (
                    <span
                      aria-disabled="true"
                      title="Not in the new app yet - open it in the classic app"
                      className="flex min-h-[44px] items-center justify-between gap-2 rounded-md px-3 text-sm text-ink-muted"
                    >
                      {item.label}
                      <span className="rounded bg-ink-2 px-1.5 py-0.5 text-[10px] font-bold tracking-wide uppercase">
                        Soon
                      </span>
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
    </aside>
  );
}

function TopBar() {
  const { user, logout } = useAuth();
  const [theme, setTheme] = useState<Theme>('system');
  const nextTheme: Theme = theme === 'dark' ? 'light' : 'dark';

  return (
    <header className="flex min-h-16 items-center justify-end gap-3 border-b border-line bg-surface px-6">
      <div className="mr-auto text-sm text-muted">
        Signed in as <strong className="text-fg">{user?.first_name || user?.username}</strong>
        {user?.role && (
          <span className="ml-2 rounded-full border border-line bg-surface-2 px-2.5 py-0.5 text-xs font-semibold text-fg">
            {user.role.replace(/_/g, ' ')}
          </span>
        )}
      </div>
      <Button
        variant="ghost"
        aria-label={`Switch to ${nextTheme} theme`}
        onClick={() => {
          setTheme(nextTheme);
          applyTheme(nextTheme);
        }}
      >
        {theme === 'dark' ? (
          <Sun className="size-5" aria-hidden />
        ) : (
          <Moon className="size-5" aria-hidden />
        )}
      </Button>
      <Button onClick={() => void logout()}>
        <LogOut className="size-4" aria-hidden /> Log out
      </Button>
    </header>
  );
}

export function AppShell() {
  return (
    <div className="flex h-full">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main id="main" className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

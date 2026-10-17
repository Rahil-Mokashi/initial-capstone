import { ChecksUpdating } from '@/components/ChecksUpdating';
import {
  CircleDot,
  Fuel,
  LifeBuoy,
  Lock,
  LogOut,
  Moon,
  Sun,
  UserCircle2,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useConnection } from '@/api/connection';
import { useGet } from '@/api/hooks';
import { useLiveUpdates } from '@/api/live';
import type { components } from '@/api/schema';
import { useAuth } from '@/auth/AuthContext';
import { GlobalSearch } from '@/components/GlobalSearch';
import { Menu } from '@/components/ui/Menu';
import { AlertStrip, AlertsMenu } from '@/features/alerts/alerts';
import { ChangePasswordDialog, SetPinDialog } from '@/features/auth/AccountDialogs';
import { LockOverlay } from '@/features/auth/LockOverlay';
import { cn } from '@/lib/cn';
import { formatDateTime } from '@/lib/format';
import { isDark, setTheme } from '@/lib/theme';
import { visibleGroups } from './nav';
import { Button } from './ui/Button';

function NavItemLink({ to, label }: { to: string; label: string }) {
  const location = useLocation();
  return (
    <NavLink
      to={to}
      end={to === '/'}
      className={({ isActive }) =>
        cn(
          'flex min-h-[44px] items-center rounded-md px-3 text-sm font-medium',
          // Two entries can open one screen on different tabs (?tab=...); then the tab decides.
          (to.includes('?') ? to === location.pathname + location.search : isActive)
            ? 'bg-primary text-primary-fg'
            : 'text-ink-fg hover:bg-ink-2',
        )
      }
    >
      {label}
    </NavLink>
  );
}

function Sidebar() {
  const { can, user } = useAuth();
  const groups = visibleGroups(can, user?.role);
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
        <ul className="mb-5 flex flex-col gap-0.5">
          <li>
            <NavItemLink to="/" label="Today" />
          </li>
        </ul>
        {groups.map((group) => (
          <div key={group.label} className="mb-5">
            <p className="px-3 pb-1.5 text-xs font-bold tracking-widest text-ink-muted uppercase">
              {group.label}
            </p>
            <ul className="flex flex-col gap-0.5">
              {group.items.map((item) => (
                <li key={item.label}>
                  {item.to ? (
                    <NavItemLink to={item.to} label={item.label} />
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
      <div className="border-t border-ink-2 px-3 py-3">
        <NavLink
          to="/support"
          className={({ isActive }) =>
            cn(
              'flex min-h-[44px] items-center gap-2 rounded-md px-3 text-sm font-medium',
              isActive ? 'bg-primary text-primary-fg' : 'text-ink-fg hover:bg-ink-2',
            )
          }
        >
          <LifeBuoy className="size-4" aria-hidden /> Support
        </NavLink>
      </div>
    </aside>
  );
}

function Clock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);
  const text = new Intl.DateTimeFormat(undefined, {
    weekday: 'short',
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(now);
  return <span className="num hidden text-sm text-muted xl:inline">{text}</span>;
}

/** Whether a shift is open right now, without opening the Shifts screen (hidden for roles without shift.view). */
function ShiftIndicator() {
  const summary = useGet<components['schemas']['SummaryOut']>(
    ['dashboard', 'summary'],
    '/dashboard/summary',
    true,
    60_000,
  );
  if (summary.isError) return <span className="text-sm text-muted">Shift: —</span>;
  const labels = summary.data?.open_shift_labels;
  if (!labels) return null;
  const open = labels.length > 0;
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold',
        open ? 'border-ok bg-ok-bg text-ok-fg' : 'border-line bg-surface-2 text-muted',
      )}
    >
      <CircleDot className="size-3.5" aria-hidden />
      {labels.length === 0
        ? 'No shift open'
        : labels.length === 1
          ? `Shift: ${labels[0]} • Open`
          : `${labels.length} shifts open`}
    </span>
  );
}

function AccountMenu({ onDialog }: { onDialog: (d: 'password' | 'pin') => void }) {
  const { user, logout, lock } = useAuth();
  const [dark, setDark] = useState(() => isDark());
  const name = user?.first_name || user?.username || '';
  const full = [user?.first_name, user?.last_name].filter(Boolean).join(' ') || user?.username;
  return (
    <Menu
      label={`Account menu, ${name}`}
      trigger={
        <>
          <UserCircle2 className="size-5" aria-hidden /> {name}
        </>
      }
    >
      {(close) => (
        <div className="flex flex-col gap-1">
          <div className="border-b border-line px-1 pb-3">
            <p className="font-bold">{full}</p>
            {user?.role && <p className="text-sm text-muted">{user.role.replace(/_/g, ' ')}</p>}
            <p className="text-xs text-muted">
              {user?.last_login
                ? `Last sign-in: ${formatDateTime(user.last_login)}`
                : 'First sign-in on this account'}
            </p>
          </div>
          <Button
            variant="ghost"
            className="justify-start"
            onClick={() => {
              close();
              onDialog('password');
            }}
          >
            Change password
          </Button>
          <Button
            variant="ghost"
            className="justify-start"
            onClick={() => {
              close();
              onDialog('pin');
            }}
          >
            {user?.has_pin ? 'Change quick sign-in PIN' : 'Set a quick sign-in PIN'}
          </Button>
          <Button
            variant="ghost"
            className="justify-start"
            aria-pressed={dark}
            onClick={() => {
              setTheme(dark ? 'light' : 'dark');
              setDark(!dark);
            }}
          >
            {dark ? (
              <Sun className="size-4" aria-hidden />
            ) : (
              <Moon className="size-4" aria-hidden />
            )}{' '}
            Dark mode: {dark ? 'on' : 'off'}
          </Button>
          <Button
            variant="ghost"
            className="justify-start"
            onClick={() => {
              close();
              lock();
            }}
          >
            <Lock className="size-4" aria-hidden /> Lock
          </Button>
          <Button variant="ghost" className="justify-start" onClick={() => void logout()}>
            <LogOut className="size-4" aria-hidden /> Log out
          </Button>
        </div>
      )}
    </Menu>
  );
}

/** Single PC: nothing (the old "offline" chip was removed). Client PC: whether the Main PC is reachable, and when the screen last heard from it. */
function ConnectionBadge() {
  const { link, lastOk } = useConnection();
  if (link === 'local') return null;
  const look = {
    live: { tone: 'bg-ok-bg text-ok-fg border-ok', dot: 'bg-ok-fg', text: 'Main PC connected' },
    polling: { tone: 'bg-warn-bg text-warn-fg border-warn', dot: 'bg-warn-fg', text: 'Main PC connected (refreshing every 20 s)' },
    offline: { tone: 'bg-danger-bg text-danger-fg border-danger', dot: 'bg-danger-fg', text: 'Main PC not reachable - read only' },
  }[link];
  const updated = lastOk ? new Date(lastOk).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : null;
  return (
    <span role="status" className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold ${look.tone}`} title="Your data is on the pump's Main PC. This PC keeps no copy.">
      <span className={`size-2 rounded-full ${look.dot}`} aria-hidden />
      {look.text}
      {updated && <span className="font-normal">· updated {updated}</span>}
    </span>
  );
}

function OfflineStrip() {
  const { link } = useConnection();
  if (link !== 'offline') return null;
  return (
    <p role="alert" className="border-b border-danger bg-danger-bg px-6 py-2 text-sm font-medium text-danger-fg">
      The Main PC cannot be reached. You can still read what is on screen, but nothing can be saved until it is back. Trying again every few seconds.
    </p>
  );
}

function TopBar() {
  const [dialog, setDialog] = useState<'password' | 'pin' | null>(null);
  return (
    <>
      <header className="flex min-h-16 flex-wrap items-center gap-3 border-b border-line bg-surface px-6 py-2">
        <GlobalSearch />
        <div className="ml-auto flex flex-wrap items-center gap-3">
          <ChecksUpdating />
          <ConnectionBadge />
          <ShiftIndicator />
          <Clock />
          <AlertsMenu />
          <AccountMenu onDialog={setDialog} />
        </div>
      </header>
      {dialog === 'password' && <ChangePasswordDialog onClose={() => setDialog(null)} />}
      {dialog === 'pin' && <SetPinDialog onClose={() => setDialog(null)} />}
    </>
  );
}

export function AppShell() {
  const { locked } = useAuth();
  useLiveUpdates();
  return (
    <>
      {/* While locked nothing behind the overlay can be reached by mouse, keyboard or screen reader. */}
      <div className="flex h-full" inert={locked}>
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar />
          <OfflineStrip />
          <AlertStrip />
          <main id="main" className="flex-1 overflow-y-auto p-6">
            <Outlet />
          </main>
        </div>
      </div>
      {locked && <LockOverlay />}
    </>
  );
}

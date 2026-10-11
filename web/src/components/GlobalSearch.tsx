import { Search } from 'lucide-react';
import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useGet } from '@/api/hooks';
import type { Tank } from '@/api/types';
import { useAuth } from '@/auth/AuthContext';
import { P } from '@/lib/permissions';
import type { EmployeeRecord } from '@/features/employees/queries';
import type { UserRecord } from '@/features/users/queries';

interface Entry {
  label: string;
  to: string;
}

/**
 * One search box over the records this person may see (employees, nozzles, tanks, user accounts), like the Qt
 * top bar. Picking a result opens that module's screen. Each list is only requested when the matching
 * permission is held, so the box can never reveal a record the sidebar would have hidden. Ctrl+F focuses it.
 */
export function GlobalSearch() {
  const { can } = useAuth();
  const navigate = useNavigate();
  const employees = useGet<EmployeeRecord[]>(
    ['employees', 'list'],
    '/employees',
    can(P.EMPLOYEE_VIEW),
  );
  const nozzles = useGet<Array<{ code: string }>>(
    ['nozzles', 'nozzles'],
    '/nozzles',
    can(P.NOZZLE_VIEW),
  );
  const tanks = useGet<Tank[]>(['tanks', 'list'], '/tanks', can(P.INVENTORY_VIEW));
  const users = useGet<UserRecord[]>(['users', 'list'], '/users', can(P.USER_MANAGE));
  const [text, setText] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();

  const index = useMemo<Entry[]>(
    () => [
      ...(employees.data ?? []).map((e) => ({
        label: `${e.first_name} ${e.last_name}  ·  ${e.employee_code}`,
        to: '/employees',
      })),
      ...(nozzles.data ?? []).map((n) => ({ label: `Nozzle ${n.code}`, to: '/nozzles' })),
      ...(tanks.data ?? []).map((t) => ({ label: `Tank ${t.code}`, to: '/tanks' })),
      ...(users.data ?? []).map((u) => ({ label: `${u.username}  ·  user account`, to: '/users' })),
    ],
    [employees.data, nozzles.data, tanks.data, users.data],
  );
  const results = useMemo(() => {
    const q = text.trim().toLowerCase();
    return q
      ? index
          .filter((e) => e.label.toLowerCase().includes(q))
          .sort((a, b) => a.label.localeCompare(b.label))
          .slice(0, 8)
      : [];
  }, [index, text]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
        e.preventDefault();
        input.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  function choose(entry: Entry) {
    setText('');
    setOpen(false);
    navigate(entry.to);
  }

  return (
    <div className="relative w-72 max-w-full">
      <label htmlFor={`${listId}-input`} className="sr-only">
        Search employees, nozzles, tanks
      </label>
      <Search
        className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted"
        aria-hidden
      />
      <input
        ref={input}
        id={`${listId}-input`}
        type="search"
        role="combobox"
        aria-expanded={open && results.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        autoComplete="off"
        placeholder="Search employees, nozzles, tanks…"
        title="Search (Ctrl+F)"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setOpen(true);
          setActive(0);
        }}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') {
            e.preventDefault();
            setActive((a) => Math.min(a + 1, results.length - 1));
          } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setActive((a) => Math.max(a - 1, 0));
          } else if (e.key === 'Enter' && open && results[active]) {
            e.preventDefault();
            choose(results[active]);
          } else if (e.key === 'Escape') {
            setOpen(false);
          }
        }}
        className="min-h-[44px] w-full rounded-md border border-line-strong bg-surface pr-3 pl-9 text-sm"
      />
      {open && results.length > 0 && (
        <ul
          id={listId}
          role="listbox"
          aria-label="Search results"
          className="absolute z-30 mt-1 w-full overflow-hidden rounded-md border border-line bg-surface shadow-pop"
        >
          {results.map((r, i) => (
            <li
              key={r.label}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(r);
              }}
              className={`cursor-pointer px-3 py-2 text-sm ${i === active ? 'bg-surface-2' : ''}`}
            >
              {r.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

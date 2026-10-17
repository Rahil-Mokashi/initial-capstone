import { Search } from 'lucide-react';
import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useGet } from '@/api/hooks';
import { useAuth } from '@/auth/AuthContext';
import {
  getRecentSearches,
  pageEntries,
  rememberSearch,
  search,
  type SearchEntry,
} from '@/lib/search';

type RecordRow = { kind: string; label: string; hint: string; to: string };

/**
 * One search box over every screen and common action this person may open, and the records the server says they may see
 * (employees, users, customers, vehicles, nozzles, dispensers, tanks, suppliers). It forgives typos and knows the pump's other
 * words (petrol = MS, diesel = HSD, salary = payroll, udhaar = credit). Ctrl+K (or Ctrl+F) focuses it; arrow keys and Enter
 * choose; the last five searches are offered when the box is empty. Nothing leaves this PC.
 */
export function GlobalSearch() {
  const { can, user } = useAuth();
  const navigate = useNavigate();
  const who = user?.username ?? '';
  const records = useGet<RecordRow[]>(['search', 'records'], '/search/records');
  const [text, setText] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [recent, setRecent] = useState<string[]>([]);
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();

  const index = useMemo<SearchEntry[]>(
    () => [...pageEntries(can, user?.role), ...(records.data ?? [])],
    // `can` is stable per user; the permission list is what matters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [records.data, user?.permissions, user?.role],
  );
  const results = useMemo(() => search(index, text), [index, text]);
  const showingRecent = open && text.trim() === '' && recent.length > 0;
  const rows: Array<{ key: string; main: string; side?: string; run: () => void }> = showingRecent
    ? recent.map((q) => ({ key: `recent-${q}`, main: q, side: 'Recent', run: () => setText(q) }))
    : results.map((r) => ({
        key: `${r.kind}-${r.to}-${r.label}`,
        main: r.label,
        side: [r.kind, r.hint].filter(Boolean).join(' · '),
        run: () => choose(r),
      }));

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase();
      if ((e.ctrlKey || e.metaKey) && (k === 'k' || k === 'f')) {
        e.preventDefault();
        input.current?.focus();
        input.current?.select();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  function reopen() {
    setRecent(getRecentSearches(who));
    setOpen(true);
    void records.refetch();
  }

  function choose(entry: SearchEntry) {
    rememberSearch(who, text);
    setText('');
    setOpen(false);
    navigate(entry.to);
  }

  return (
    <div className="relative w-80 max-w-full">
      <label htmlFor={`${listId}-input`} className="sr-only">
        Search screens, actions and records
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
        aria-expanded={open && rows.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        autoComplete="off"
        placeholder="Search screens, actions, people…"
        title="Search (Ctrl+K)"
        value={text}
        onFocus={reopen}
        onClick={reopen}
        onChange={(e) => {
          setText(e.target.value);
          setOpen(true);
          setActive(0);
        }}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') {
            e.preventDefault();
            setActive((a) => Math.min(a + 1, rows.length - 1));
          } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setActive((a) => Math.max(a - 1, 0));
          } else if (e.key === 'Enter' && open && rows[active]) {
            e.preventDefault();
            rows[active]!.run();
          } else if (e.key === 'Escape') {
            setOpen(false);
          }
        }}
        className="min-h-[44px] w-full rounded-md border border-line-strong bg-surface pr-3 pl-9 text-sm"
      />
      {open && rows.length > 0 && (
        <ul
          id={listId}
          role="listbox"
          aria-label={showingRecent ? 'Recent searches' : 'Search results'}
          className="absolute z-30 mt-1 w-full overflow-hidden rounded-md border border-line bg-surface shadow-pop"
        >
          {rows.map((r, i) => (
            <li
              key={r.key}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => {
                e.preventDefault();
                r.run();
              }}
              className={`flex cursor-pointer items-baseline justify-between gap-3 px-3 py-2 text-sm ${i === active ? 'bg-surface-2' : ''}`}
            >
              <span>{r.main}</span>
              {r.side && <span className="shrink-0 text-xs text-muted">{r.side}</span>}
            </li>
          ))}
        </ul>
      )}
      {open && text.trim() !== '' && rows.length === 0 && (
        <p className="absolute z-30 mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm text-muted shadow-pop">
          Nothing found for “{text.trim()}”.
        </p>
      )}
    </div>
  );
}

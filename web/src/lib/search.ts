// The top-bar search: pages and actions the signed-in role can open, plus the records the server sent (it only sends what the role may
// see). Matching forgives typos ("employes", "nozel"), partial words and letters left out ("dsl"), and knows the pump's other words
// for things (petrol = MS, diesel = HSD, salary = payroll, udhaar = credit). Everything happens in the browser; nothing leaves the PC.
import { visibleGroups } from '@/components/nav';

export interface SearchEntry {
  /** Page | Action | Employee | User | Customer | Vehicle | Nozzle | Dispenser | Tank | Supplier */
  kind: string;
  label: string;
  hint?: string;
  to: string;
  /** Extra words that should find it. */
  keywords?: string;
}

interface ActionDef {
  label: string;
  to: string;
  permission: string;
  keywords: string;
}

// Things people do, found by what they would type. Each needs the permission that does the thing.
const ACTIONS: ActionDef[] = [
  { label: 'Open a shift', to: '/shifts', permission: 'shift.manage', keywords: 'start begin new shift' },
  { label: 'Close a shift', to: '/close-shift', permission: 'shift.manage', keywords: 'end finish closing readings' },
  { label: 'Add an employee', to: '/employees', permission: 'employee.manage', keywords: 'new staff hire worker attendant' },
  { label: 'Mark attendance', to: '/attendance', permission: 'attendance.manage', keywords: 'present absent late' },
  { label: 'Record a dip reading', to: '/tanks', permission: 'inventory.manage', keywords: 'dip stick measure tank level' },
  { label: 'Receive a tanker delivery', to: '/tanks', permission: 'inventory.manage', keywords: 'receipt stock fuel delivery unload' },
  { label: 'Change a fuel price', to: '/fuel-prices', permission: 'fuel_price.manage', keywords: 'rate price petrol diesel' },
  { label: 'Make a credit sale', to: '/terminal', permission: 'sale.manage', keywords: 'bill terminal quick sale dtp vehicle' },
  { label: 'Add a credit customer', to: '/credit', permission: 'credit.manage', keywords: 'new customer account limit' },
  { label: 'Take a payment from a customer', to: '/credit', permission: 'credit.manage', keywords: 'receive money collect credit payment' },
  { label: 'Record an expense', to: '/expenses', permission: 'expense.manage', keywords: 'spend cost' },
  { label: 'Prepare salaries', to: '/payroll', permission: 'payroll.manage', keywords: 'payroll salary wages pay month' },
  { label: 'Add a user', to: '/users', permission: 'user.manage', keywords: 'new login account password role' },
  { label: 'Take a backup', to: '/backups', permission: 'backup.manage', keywords: 'copy save restore' },
];

// Other words for the same thing. Applied to what the person types.
const SYNONYMS: Record<string, string[]> = {
  petrol: ['ms'],
  gasoline: ['ms'],
  ms: ['petrol'],
  diesel: ['hsd'],
  hsd: ['diesel'],
  salary: ['payroll'],
  salaries: ['payroll'],
  wages: ['payroll'],
  udhaar: ['credit'],
  udhar: ['credit'],
  khata: ['credit'],
  staff: ['employees', 'employee'],
  worker: ['employees', 'employee'],
  stock: ['tanks', 'tank'],
  dip: ['tank', 'tanks'],
  rate: ['price', 'prices'],
  sale: ['sales'],
  bill: ['credit', 'sales'],
  cashier: ['users', 'user'],
};

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9\s]/g, ' ');
const words = (s: string) => norm(s).split(/\s+/).filter(Boolean);

/** Edit distance, capped: enough to tell "nozel" from "nozzle" without a library. */
export function distance(a: string, b: string): number {
  if (Math.abs(a.length - b.length) > 2) return 3;
  let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    for (let j = 1; j <= b.length; j++) {
      cur[j] = Math.min(prev[j]! + 1, cur[j - 1]! + 1, prev[j - 1]! + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
    prev = cur;
  }
  return prev[b.length]!;
}

function isSubsequence(token: string, word: string): boolean {
  if (token[0] !== word[0]) return false;
  let i = 0;
  for (const c of word) if (c === token[i]) i++;
  return i === token.length;
}

/** 0 = no match; higher is closer. */
function scoreWord(token: string, word: string): number {
  if (word === token) return 100;
  if (word.startsWith(token)) return 80;
  if (token.length < 3) return 0;
  const d = distance(token, word);
  if (d <= (token.length <= 4 ? 1 : 2)) return 70 - d * 10;
  if (word.length > token.length && distance(token, word.slice(0, token.length)) <= 1) return 55;
  if (token.length >= 3 && isSubsequence(token, word)) return 40;
  return 0;
}

export function entryScore(query: string, entry: SearchEntry): number {
  const haystack = words(`${entry.label} ${entry.hint ?? ''} ${entry.kind} ${entry.keywords ?? ''}`);
  let total = 0;
  for (const token of words(query)) {
    const alternatives = [token, ...(SYNONYMS[token] ?? [])];
    let best = 0;
    for (const alt of alternatives) for (const w of haystack) best = Math.max(best, scoreWord(alt, w));
    if (best === 0) return 0; // every typed word has to find something
    total += best;
  }
  return total;
}

const KIND_RANK: Record<string, number> = { Page: 0, Action: 1 };

export function search(entries: SearchEntry[], query: string, limit = 8): SearchEntry[] {
  if (!query.trim()) return [];
  return entries
    .map((e) => ({ e, s: entryScore(query, e) }))
    .filter((x) => x.s > 0)
    .sort((a, b) => b.s - a.s || (KIND_RANK[a.e.kind] ?? 2) - (KIND_RANK[b.e.kind] ?? 2) || a.e.label.localeCompare(b.e.label))
    .slice(0, limit)
    .map((x) => x.e);
}

/** Every screen and action this role can open. Same rules as the sidebar, so it never offers a door that is closed. */
export function pageEntries(can: (permission: string) => boolean, role?: string | null): SearchEntry[] {
  const pages: SearchEntry[] = visibleGroups(can, role).flatMap((g) =>
    g.items
      .filter((i) => i.to)
      .map((i) => ({ kind: 'Page', label: i.label, hint: g.label, to: i.to! })),
  );
  const actions: SearchEntry[] = ACTIONS.filter((a) => can(a.permission)).map((a) => ({
    kind: 'Action', label: a.label, to: a.to, keywords: a.keywords,
  }));
  return [...pages, ...actions];
}

// ---- the last five searches, kept per signed-in person in this browser only
const recentKey = (who: string) => `pperp.search.recent.${who}`;

export function getRecentSearches(who: string): string[] {
  try {
    const raw = JSON.parse(window.localStorage.getItem(recentKey(who)) ?? '[]') as unknown;
    return Array.isArray(raw) ? raw.filter((x): x is string => typeof x === 'string').slice(0, 5) : [];
  } catch {
    return [];
  }
}

export function rememberSearch(who: string, query: string): void {
  const q = query.trim();
  if (!q) return;
  try {
    const next = [q, ...getRecentSearches(who).filter((x) => x.toLowerCase() !== q.toLowerCase())].slice(0, 5);
    window.localStorage.setItem(recentKey(who), JSON.stringify(next));
  } catch {
    /* storage can be unavailable; the search still works */
  }
}

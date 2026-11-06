// DISPLAY formatting only. Amounts and volumes arrive from the server as exact
// decimal strings; they are never converted to JS numbers, so no float error can
// creep in. Grouping is done on the digits of the string.

const DECIMAL = /^-?\d+(\.\d+)?$/;

/** Every date and time on screen uses this one locale, never the PC's own (same look on every pump PC and in CI). */
export const DISPLAY_LOCALE = 'en-IN';

/** 1234567 -> "12,34,567": the last three digits, then pairs (the Qt app's Indian grouping). */
function groupIndian(digits: string): string {
  if (digits.length <= 3) return digits;
  const last = digits.slice(-3);
  const rest = digits.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ',');
  return `${rest},${last}`;
}

export function groupDigits(value: string): string {
  if (!DECIMAL.test(value)) return value;
  const negative = value.startsWith('-');
  const [int = '', frac] = (negative ? value.slice(1) : value).split('.');
  const grouped = groupIndian(int);
  return `${negative ? '-' : ''}${grouped}${frac !== undefined ? `.${frac}` : ''}`;
}

/** "2500.500" -> "2,500.500" ; with sign: "+100.000" / "-200.000". */
export function formatQuantity(value: string, opts: { signed?: boolean } = {}): string {
  const out = groupDigits(value);
  return opts.signed && DECIMAL.test(value) && !value.startsWith('-') && !/^0+(\.0+)?$/.test(value)
    ? `+${out}`
    : out;
}

export function formatLitres(value: string): string {
  return `${groupDigits(value)} L`;
}

/** "25.01" -> "25.0%" (one place is plenty on a gauge; rounding is string-safe). */
export function formatPercent(value: string): string {
  if (!DECIMAL.test(value)) return value;
  const [int = '0', frac = ''] = value.split('.');
  const first = frac.charAt(0) || '0';
  const roundUp = Number(frac.charAt(1) || '0') >= 5;
  if (!roundUp) return `${int}.${first}%`;
  const tenths = BigInt(int + first) + 1n;
  const s = tenths.toString().padStart(2, '0');
  return `${s.slice(0, -1)}.${s.slice(-1)}%`;
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat(DISPLAY_LOCALE, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(d);
}

export function formatDate(isoDate: string): string {
  const d = new Date(`${isoDate}T00:00:00`);
  return Number.isNaN(d.getTime())
    ? isoDate
    : new Intl.DateTimeFormat(DISPLAY_LOCALE, {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
      }).format(d);
}

export function todayIso(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function titleCase(value: string): string {
  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace(/\bDtp\b/g, 'DTP');
}

export interface DecimalRules {
  /** Allow a leading minus (only stock adjustments). */
  negative?: boolean;
  /** Reject zero. */
  nonZero?: boolean;
}

/** Same limits the server enforces: at most 9 whole digits and 3 places. */
export function checkDecimal(raw: string, rules: DecimalRules = {}): string | null {
  const value = raw.trim();
  if (value === '') return 'Enter a number.';
  if (!/^-?\d{1,9}(\.\d{1,3})?$/.test(value)) {
    return rules.negative
      ? 'Use digits with at most 3 decimal places, for example 1250.500 or -2.5.'
      : 'Use digits with at most 3 decimal places, for example 1250.500.';
  }
  if (value.startsWith('-') && !rules.negative) return 'This cannot be negative.';
  if (rules.nonZero && /^-?0+(\.0+)?$/.test(value)) return 'This cannot be zero.';
  return null;
}

/** "104.5" -> "₹104.5" ; the string keeps the server's places (money arrives with 2). */
export function formatMoney(value: string): string {
  return `₹${groupDigits(value)}`;
}

/** Today plus `days` as YYYY-MM-DD (local), for default due dates and the like. */
export function addDaysIso(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

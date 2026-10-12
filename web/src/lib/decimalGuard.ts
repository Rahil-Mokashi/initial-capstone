// Keeps a number box from ever holding more decimal places than the database stores
// (volume 3, money 2). The text is NEVER rounded or cut: a key press or paste that would break the
// rule is simply refused, and the person is told why.

export interface DecimalGuardRules {
  /** Decimal places allowed: 3 for litres (app/core/money.py VOLUME_QUANTUM), 2 for money. */
  maxFraction: number;
  /** Whole-number digits allowed (Numeric(12, 3) leaves 9). */
  maxInteger?: number;
  /** Allow a leading minus (only stock adjustments). */
  negative?: boolean;
}

export type GuardResult =
  { ok: true } | { ok: false; reason: 'characters' | 'fraction' | 'integer' | 'minus' };

/** The text a box would hold after `inserted` replaces the selection [start, end). */
export function applyEdit(current: string, start: number, end: number, inserted: string): string {
  return current.slice(0, start) + inserted + current.slice(end);
}

/** Is `text` an acceptable value, or a prefix of one ("", "-", "12.", ".5" are all fine while typing)? */
export function checkPartialDecimal(text: string, rules: DecimalGuardRules): GuardResult {
  const maxInteger = rules.maxInteger ?? 9;
  let body = text;
  if (body.startsWith('-')) {
    if (!rules.negative) return { ok: false, reason: 'minus' };
    body = body.slice(1);
  }
  if (!/^\d*\.?\d*$/.test(body)) return { ok: false, reason: 'characters' };
  const [whole = '', fraction = ''] = body.split('.');
  if (whole.length > maxInteger) return { ok: false, reason: 'integer' };
  if (fraction.length > rules.maxFraction) return { ok: false, reason: 'fraction' };
  return { ok: true };
}

export function explain(
  result: GuardResult,
  rules: DecimalGuardRules,
  unit = 'litres',
): string | null {
  if (result.ok) return null;
  const places =
    rules.maxFraction === 1 ? '1 decimal place' : `${rules.maxFraction} decimal places`;
  const example = rules.maxFraction === 2 ? '1250.50' : '1250.500';
  switch (result.reason) {
    case 'fraction':
      return `${unit[0]?.toUpperCase()}${unit.slice(1)} can have at most ${places} (for example ${example}). Extra digits are not accepted.`;
    case 'integer':
      return `That number is too large. Use at most ${rules.maxInteger ?? 9} digits before the decimal point.`;
    case 'minus':
      return 'This cannot be negative.';
    default:
      return 'Type digits only, with one decimal point.';
  }
}

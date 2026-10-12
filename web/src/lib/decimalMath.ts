// Exact decimal arithmetic on strings, for DISPLAY previews only (the Terminal's live
// "Volume / Total" line). Same result as Python's Decimal(...).quantize(Decimal("0.01")),
// i.e. rounded half-even to two places. The server does the real calculation on save.

interface Scaled {
  n: bigint;
  scale: number;
}

function parse(value: string): Scaled | null {
  const m = /^(\d+)(?:\.(\d+))?$/.exec(value.trim());
  if (!m) return null;
  const frac = m[2] ?? '';
  return { n: BigInt(m[1]! + frac), scale: frac.length };
}

const pow10 = (n: number) => 10n ** BigInt(n);

/** round(num / den) to the nearest integer, ties to even. den > 0. */
function divHalfEven(num: bigint, den: bigint): bigint {
  const q = num / den;
  const r2 = (num % den) * 2n;
  if (r2 > den || (r2 === den && q % 2n !== 0n)) return q + 1n;
  return q;
}

function format2(hundredths: bigint): string {
  const s = hundredths.toString().padStart(3, '0');
  return `${s.slice(0, -2)}.${s.slice(-2)}`;
}

/** a / b rounded to 2 places, or null for bad input or a zero divisor. */
export function divide2(a: string, b: string): string | null {
  const x = parse(a);
  const y = parse(b);
  if (!x || !y || y.n === 0n) return null;
  // (X / 10^sx) / (Y / 10^sy) * 100 = X * 10^sy * 100 / (Y * 10^sx)
  return format2(divHalfEven(x.n * pow10(y.scale) * 100n, y.n * pow10(x.scale)));
}

/** a * b rounded to 2 places, or null for bad input. */
export function multiply2(a: string, b: string): string | null {
  const x = parse(a);
  const y = parse(b);
  if (!x || !y) return null;
  // X * Y / 10^(sx+sy) * 100
  const scale = x.scale + y.scale;
  return format2(divHalfEven(x.n * y.n * 100n, pow10(scale)));
}

/** Exact total of money strings that already have two places (the server's), e.g. a list's outstanding balances. */
export function sumMoney(values: string[]): string {
  let total = 0n;
  for (const v of values) {
    const m = /^(-?)(\d+)\.(\d{2})$/.exec(v.trim());
    if (!m) continue;
    const cents = BigInt(m[2]! + m[3]!);
    total += m[1] ? -cents : cents;
  }
  const neg = total < 0n;
  return `${neg ? '-' : ''}${format2(neg ? -total : total)}`;
}

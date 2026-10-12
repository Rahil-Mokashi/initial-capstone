// Meaning copied from the Qt Tanks window (app/ui/widgets.py: variance_bar_fractions,
// _VARIANCE_COLOR_TONE, VarianceBarCard) - not invented here.
//
//  * Two bars, Book (expected) and Physical (dipped), each drawn as a fraction of whichever is
//    larger, so both always fit one track; negatives are clamped to 0.
//  * ONE colour for both bars, chosen by the server's classification:
//      normal                                  -> neutral (ink)
//      warning, investigation_required         -> amber
//      approval_required                       -> red
//    The classification itself (and its 0.5 / 1 / 2 % thresholds) is decided by the backend
//    (app/services/tank_service.py classify_variance); the UI only displays it.

export type VarianceTone = 'normal' | 'warning' | 'critical';

const TONE: Record<string, VarianceTone> = {
  normal: 'normal',
  warning: 'warning',
  investigation_required: 'warning',
  approval_required: 'critical',
};

export function varianceTone(classification: string): VarianceTone {
  return TONE[classification] ?? 'normal'; // same fallback as Qt's .get(classification, "normal")
}

const SCALE = 1000n; // volumes arrive with 3 decimal places

/** "2500.500" -> 2500500n, without ever going through a float. */
function toThousandths(value: string): bigint {
  const negative = value.startsWith('-');
  const [whole = '0', frac = ''] = (negative ? value.slice(1) : value).split('.');
  const n = BigInt(whole || '0') * SCALE + BigInt((frac + '000').slice(0, 3));
  return negative ? -n : n;
}

/** [book, physical] as fractions 0..1 of the larger of the two (for bar widths only). */
export function varianceFractions(expected: string, physical: string): [number, number] {
  const e = toThousandths(expected);
  const p = toThousandths(physical);
  const eClamped = e > 0n ? e : 0n;
  const pClamped = p > 0n ? p : 0n;
  const larger = eClamped > pClamped ? eClamped : pClamped;
  if (larger <= 0n) return [0, 0];
  // Integer division to 1/10000 first keeps full precision before the final conversion for CSS.
  const frac = (x: bigint) => Number((x * 10000n) / larger) / 10000;
  return [frac(eClamped), frac(pClamped)];
}

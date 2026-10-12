import { formatMoney, groupDigits } from '@/lib/format';

/** A check number in its own unit, grouped the Indian way: Rs for money, L for litres. */
export function formatCheckValue(unit: string, value: string | null | undefined): string {
  if (value == null) return 'not available';
  if (unit === 'litres') return `${groupDigits(value)} L`;
  if (unit === 'count') return groupDigits(value);
  return formatMoney(value);
}

export function statusWords(status: string): string {
  return status === 'pass' ? 'Passed' : status === 'warn' ? 'Look at this' : 'Failed';
}

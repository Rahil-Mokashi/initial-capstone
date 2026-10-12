import { describe, expect, it } from 'vitest';
import { divide2, multiply2 } from './decimalMath';

describe('decimalMath', () => {
  it('divides like Decimal.quantize(0.01): exact, half-even', () => {
    expect(divide2('500', '100')).toBe('5.00');
    expect(divide2('500.00', '103.50')).toBe('4.83'); // 4.8309...
    expect(divide2('1', '3')).toBe('0.33');
    expect(divide2('2', '3')).toBe('0.67');
    expect(divide2('1.00', '8')).toBe('0.12'); // 0.125 -> tie -> even
    expect(divide2('3.00', '8')).toBe('0.38'); // 0.375 -> tie -> even
  });
  it('multiplies and rounds to two places', () => {
    expect(multiply2('12.50', '100.00')).toBe('1250.00');
    expect(multiply2('4.887', '102.30')).toBe('499.94'); // 499.9401
    expect(multiply2('0.005', '1')).toBe('0.00'); // tie -> even
    expect(multiply2('0.015', '1')).toBe('0.02'); // tie -> even
  });
  it('refuses nonsense and a zero rate', () => {
    expect(divide2('abc', '1')).toBeNull();
    expect(divide2('5', '0')).toBeNull();
    expect(multiply2('', '1')).toBeNull();
  });
});

describe('sumMoney', () => {
  it('adds money strings exactly, with no float error', async () => {
    const { sumMoney } = await import('./decimalMath');
    expect(sumMoney(['0.10', '0.20'])).toBe('0.30');
    expect(sumMoney(['1500.00', '1234567.89', '-0.01'])).toBe('1236067.88');
    expect(sumMoney([])).toBe('0.00');
  });
});

import { describe, expect, it } from 'vitest';
import {
  checkDecimal,
  formatDate,
  formatLitres,
  formatPercent,
  formatQuantity,
  groupDigits,
  titleCase,
} from './format';

describe('display formatting works on strings (no floats)', () => {
  it('groups digits and keeps every decimal place', () => {
    expect(groupDigits('1234567.500')).toBe('12,34,567.500'); // Indian grouping, as in the Qt tables
    expect(groupDigits('100000')).toBe('1,00,000');
    expect(groupDigits('2500')).toBe('2,500');
    expect(groupDigits('999')).toBe('999');
    expect(groupDigits('-10000.000')).toBe('-10,000.000');
    expect(groupDigits('0.001')).toBe('0.001');
  });
  it('keeps precision beyond what a float can hold', () => {
    expect(groupDigits('9007199254740993.001')).toBe('9,00,71,99,25,47,40,993.001');
  });
  it('signs quantities', () => {
    expect(formatQuantity('100.000', { signed: true })).toBe('+100.000');
    expect(formatQuantity('-200.000', { signed: true })).toBe('-200.000');
    expect(formatQuantity('0.000', { signed: true })).toBe('0.000');
  });
  it('formats litres and percent', () => {
    expect(formatLitres('2500.500')).toBe('2,500.500 L');
    expect(formatPercent('25.01')).toBe('25.0%');
    expect(formatPercent('99.95')).toBe('100.0%');
    expect(formatPercent('0.04')).toBe('0.0%');
    expect(formatPercent('18.00')).toBe('18.0%');
  });
  it('leaves non-numbers alone instead of inventing output', () => {
    expect(groupDigits('n/a')).toBe('n/a');
  });
  it('title-cases enum values', () => {
    expect(titleCase('investigation_required')).toBe('Investigation Required');
  });
});

describe('checkDecimal mirrors the server limits', () => {
  it.each(['0', '1', '1250.500', '123456789.123', ' 12.5 '])('accepts %j', (v) => {
    expect(checkDecimal(v)).toBeNull();
  });
  it.each(['', 'abc', '1.2345', '1234567890', '1,000', '1e3', '.5', '-'])('rejects %j', (v) => {
    expect(checkDecimal(v)).not.toBeNull();
  });
  it('allows negatives only when asked', () => {
    expect(checkDecimal('-5', {})).toMatch(/negative/);
    expect(checkDecimal('-5', { negative: true })).toBeNull();
  });
  it('allows zero only when asked', () => {
    expect(checkDecimal('0.000', { nonZero: true })).toMatch(/zero/);
    expect(checkDecimal('-0', { negative: true, nonZero: true })).toMatch(/zero/);
  });
});

describe('dates read the same on every PC', () => {
  it('formats dates in the fixed display locale, not the machine one', () => {
    expect(formatDate('2026-10-11')).toBe('11 Oct 2026');
    expect(formatDate('not-a-date')).toBe('not-a-date');
  });
});

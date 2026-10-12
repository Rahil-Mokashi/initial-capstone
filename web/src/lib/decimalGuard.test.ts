import { describe, expect, it } from 'vitest';
import { applyEdit, checkPartialDecimal, explain } from './decimalGuard';

const litres = { maxFraction: 3 };
const money = { maxFraction: 2 };

describe('checkPartialDecimal', () => {
  it.each([
    '',
    '1',
    '12',
    '12.',
    '12.5',
    '12.50',
    '12.500',
    '.5',
    '123456789',
    '123456789.123',
    '0',
  ])('accepts %j while typing', (text) => expect(checkPartialDecimal(text, litres).ok).toBe(true));

  it('refuses a fourth decimal place for litres and a third for money', () => {
    expect(checkPartialDecimal('1.2345', litres)).toEqual({ ok: false, reason: 'fraction' });
    expect(checkPartialDecimal('1.234', money)).toEqual({ ok: false, reason: 'fraction' });
    expect(checkPartialDecimal('1.23', money).ok).toBe(true);
  });

  it('refuses letters, signs, a second point, separators and exponents', () => {
    for (const text of ['abc', '1,000', '1.2.3', '1e3', '--1', '+1']) {
      expect(checkPartialDecimal(text, { ...litres, negative: true }).ok, text).toBe(false);
    }
  });

  it('refuses a minus unless negatives are allowed', () => {
    expect(checkPartialDecimal('-5', litres)).toEqual({ ok: false, reason: 'minus' });
    expect(checkPartialDecimal('-', { ...litres, negative: true }).ok).toBe(true);
    expect(checkPartialDecimal('-5.250', { ...litres, negative: true }).ok).toBe(true);
  });

  it('limits the whole-number digits to what the column holds', () => {
    expect(checkPartialDecimal('1234567890', litres)).toEqual({ ok: false, reason: 'integer' });
  });
});

describe('applyEdit', () => {
  it('inserts at the caret and replaces a selection', () => {
    expect(applyEdit('12.34', 5, 5, '5')).toBe('12.345');
    expect(applyEdit('12.345', 3, 6, '9')).toBe('12.9');
    expect(applyEdit('', 0, 0, '7')).toBe('7');
  });
  it('a paste is judged whole, never trimmed to fit', () => {
    const result = checkPartialDecimal(applyEdit('', 0, 0, '12.34567'), litres);
    expect(result.ok).toBe(false);
  });
});

describe('explain', () => {
  it('says why, with the real limit and an example', () => {
    expect(explain({ ok: false, reason: 'fraction' }, litres)).toMatch(
      /at most 3 decimal places.*1250\.500.*not accepted/,
    );
    expect(explain({ ok: false, reason: 'fraction' }, money, 'amounts')).toMatch(
      /Amounts can have at most 2 decimal places.*1250\.50/,
    );
  });
  it('is silent when everything is fine', () => {
    expect(explain({ ok: true }, litres)).toBeNull();
  });
});

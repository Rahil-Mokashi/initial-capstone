import { describe, expect, it } from 'vitest';
import { varianceFractions, varianceTone } from './variance';

describe('variance tone (same split as the Qt VarianceBarCard)', () => {
  it.each([
    ['normal', 'normal'],
    ['warning', 'warning'],
    ['investigation_required', 'warning'],
    ['approval_required', 'critical'],
  ])('%s -> %s', (classification, tone) => {
    expect(varianceTone(classification)).toBe(tone);
  });

  it('an unknown classification falls back to normal, as in Qt', () => {
    expect(varianceTone('something_new')).toBe('normal');
    expect(varianceTone('')).toBe('normal');
  });
});

describe('variance bar fractions (same maths as variance_bar_fractions)', () => {
  it('the larger of the two fills the track; the other is a fraction of it', () => {
    expect(varianceFractions('2000.500', '1990.500')).toEqual([1, 0.995]);
    expect(varianceFractions('1000.000', '2000.000')).toEqual([0.5, 1]);
  });
  it('equal stocks fill both bars', () => {
    expect(varianceFractions('500.000', '500.000')).toEqual([1, 1]);
  });
  it('both zero draws nothing instead of dividing by zero', () => {
    expect(varianceFractions('0.000', '0.000')).toEqual([0, 0]);
  });
  it('a negative figure is clamped to zero rather than drawn backwards', () => {
    expect(varianceFractions('100.000', '-5.000')).toEqual([1, 0]);
    expect(varianceFractions('-5.000', '-1.000')).toEqual([0, 0]);
  });
  it('works on exact strings, so huge or fine values lose nothing', () => {
    expect(varianceFractions('999999999.999', '999999999.998')[1]).toBeLessThan(1);
    expect(varianceFractions('10', '5')).toEqual([1, 0.5]);
  });
});

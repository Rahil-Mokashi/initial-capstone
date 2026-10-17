import { describe, expect, it } from 'vitest';
import { parseDipChartCsv } from './DipChartDialog';

describe('dip chart CSV', () => {
  it('reads dip and litres, skipping a header and blank lines, with commas, semicolons or tabs', () => {
    expect(parseDipChartCsv('Dip (cm),Litres\n0,0\n10,1250.5\n\n20;3400\n30\t6000\n')).toEqual([
      { dip_cm: '0', litres: '0' },
      { dip_cm: '10', litres: '1250.5' },
      { dip_cm: '20', litres: '3400' },
      { dip_cm: '30', litres: '6000' },
    ]);
  });
  it('ignores lines that are not numbers', () => {
    expect(parseDipChartCsv('hello\nabc,def\n')).toEqual([]);
  });
});

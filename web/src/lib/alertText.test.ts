import { describe, expect, it } from 'vitest';
import { collapsedSummaryText, sentence } from './alertText';

const a = (over = {}) => ({
  title: 'MS-16 is low on fuel.',
  detail: 'It holds 9% of capacity.',
  action: 'Place a purchase order.',
  is_summary: false,
  ...over,
});

describe('alert wording', () => {
  it('joins what, where and what to do into one sentence, without doubled full stops', () => {
    expect(sentence(a())).toBe(
      'MS-16 is low on fuel. It holds 9% of capacity. Place a purchase order.',
    );
    expect(sentence(a({ detail: '', action: '' }))).toBe('MS-16 is low on fuel.');
  });
  it('collapses to a checking line, an all-clear, one full sentence, or a count plus the most urgent', () => {
    expect(collapsedSummaryText(null)).toBe('Checking for alerts…');
    expect(collapsedSummaryText({ total: 0, notifications: [] })).toMatch(/^All clear/);
    expect(collapsedSummaryText({ total: 1, notifications: [a()] })).toBe(sentence(a()));
    expect(
      collapsedSummaryText({ total: 3, notifications: [a({ title: 'Worst thing' }), a(), a()] }),
    ).toBe('3 alerts need attention — most urgent: Worst thing.');
  });
  it('ignores the "N more" trailer when deciding what to quote', () => {
    const more = a({ title: '4 more tanks', is_summary: true });
    expect(collapsedSummaryText({ total: 2, notifications: [a(), more] })).toBe(sentence(a()));
  });
});

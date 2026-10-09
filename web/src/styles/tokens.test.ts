import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

// Reads the real tokens.css so the contrast claims in the design doc are checked, not assumed.
const css = readFileSync(resolve(process.cwd(), 'src/styles/tokens.css'), 'utf8');

function block(selectorStart: string): Record<string, string> {
  const start = css.indexOf(selectorStart);
  const open = css.indexOf('{', start);
  let depth = 0;
  let end = open;
  for (let i = open; i < css.length; i++) {
    if (css[i] === '{') depth++;
    if (css[i] === '}' && --depth === 0) {
      end = i;
      break;
    }
  }
  const vars: Record<string, string> = {};
  for (const m of css.slice(open, end).matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) {
    vars[m[1]!] = m[2]!;
  }
  return vars;
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

const light = block(':root {');
// A dark theme only overrides some tokens; the rest (for example the sidebar text) inherit.
const dark = { ...light, ...block(":root[data-theme='dark']") };
const themes: Record<string, Record<string, string>> = { light, dark };

describe('the two dark-theme definitions agree', () => {
  it('OS-preference dark and forced dark use identical values', () => {
    const forced = block(":root[data-theme='dark']");
    const auto = block('@media (prefers-color-scheme: dark)');
    expect(Object.keys(auto).length).toBeGreaterThan(10);
    expect(auto).toEqual(forced);
  });
});

describe.each(Object.entries(themes))('%s theme meets WCAG 2.1 AA', (_name, t) => {
  const text = (fg: string, bg: string, min = 4.5) =>
    expect(contrast(t[fg]!, t[bg]!), `${fg} on ${bg}`).toBeGreaterThanOrEqual(min);

  it('body and muted text on every surface', () => {
    for (const bg of ['bg', 'surface', 'surface-2']) {
      text('text', bg);
      text('text-muted', bg);
    }
  });
  it('primary button and sidebar text', () => {
    text('primary-contrast', 'primary');
    text('ink-text', 'ink');
    text('ink-muted', 'ink');
    text('ink-text', 'ink-2');
  });
  it('primary used as a link colour on surfaces', () => {
    text('primary', 'surface');
    text('primary', 'bg');
  });
  it.each(['ok', 'warn', 'danger', 'info'])('%s status text on its tinted background', (tone) => {
    text(`${tone}-text`, `${tone}-bg`);
    text(`${tone}-text`, 'surface');
  });
  it('focus ring, control borders and status colours are 3:1 against surfaces', () => {
    text('focus', 'surface', 3);
    text('focus', 'bg', 3);
    text('line-strong', 'surface', 3);
    for (const tone of ['ok', 'warn', 'danger']) text(tone, 'surface', 3);
  });
});

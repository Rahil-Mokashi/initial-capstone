import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { findExternalUrls, scan } from '../../scripts/check-offline.mjs';

describe('offline build gate', () => {
  it.each([
    'https://fonts.googleapis.com/css2?family=Inter',
    'https://cdn.jsdelivr.net/npm/react@19/index.js',
    'http://example.com/pixel.gif',
    'https://api.analytics.io/collect',
    'http://192.168.1.10:8080/x',
  ])('flags %s', (url) => {
    expect(findExternalUrls(`fetch("${url}")`, { isJs: true })).toEqual([url]);
    expect(findExternalUrls(`url(${url})`)).toEqual([url]);
  });

  it('allows loopback', () => {
    expect(findExternalUrls('http://127.0.0.1:8765/api http://localhost:5173/')).toEqual([]);
  });

  it('ignores XML namespaces', () => {
    expect(findExternalUrls('<svg xmlns="http://www.w3.org/2000/svg">')).toEqual([]);
  });

  it('allows only the exact inert library strings, and only in JS', () => {
    const inert = 'https://react.dev/errors/418?args=';
    expect(findExternalUrls(inert, { isJs: true })).toEqual([]);
    expect(findExternalUrls(inert, { isJs: false })).toHaveLength(1); // HTML and CSS get no allowance
    expect(findExternalUrls('https://react.dev.evil.com/errors/', { isJs: true })).toHaveLength(1);
    const polyfill = 'https://github.com/ungap/url-search-params';
    expect(findExternalUrls(polyfill, { isJs: true })).toEqual([]);
    expect(findExternalUrls(polyfill, { isJs: false })).toHaveLength(1);
    expect(findExternalUrls('https://github.com/ungap/other', { isJs: true })).toHaveLength(1);
  });

  it('scans a folder and reports the file', () => {
    const dir = mkdtempSync(join(tmpdir(), 'offline-'));
    try {
      writeFileSync(
        join(dir, 'index.html'),
        '<script src="https://cdn.example.com/a.js"></script>',
      );
      writeFileSync(join(dir, 'ok.js'), 'const a = "http://127.0.0.1:1"');
      expect(scan(dir)).toEqual([{ file: 'index.html', url: 'https://cdn.example.com/a.js' }]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

import { describe, expect, it } from 'vitest';
import { isAllowedNavigation, isAllowedRequest, type Policy } from './security';

const policy: Policy = {
  allowedOrigins: ['http://127.0.0.1:54321'],
  allowedFileUrls: ['file:///C:/app/dist/error.html'],
};

describe('request blocker policy (offline guarantee, second layer)', () => {
  it.each([
    'http://127.0.0.1:54321/',
    'http://127.0.0.1:54321/api/tanks',
    'http://127.0.0.1:54321/assets/index-abc.js',
  ])('allows the local API origin: %s', (url) => {
    expect(isAllowedRequest(url, policy)).toBe(true);
  });

  it.each([
    'https://example.com/',
    'http://example.com/',
    'https://fonts.googleapis.com/css2',
    'https://cdn.jsdelivr.net/npm/x',
    'http://localhost:54321/', // not the allowed hostname
    'http://127.0.0.1:9999/', // another local port is not our API
    'http://127.0.0.1.evil.com:54321/',
    'http://user@evil.com:54321@127.0.0.1:54321/',
    'ws://127.0.0.1:54321/socket',
    'wss://example.com/socket',
    'ftp://example.com/file',
    'data:text/html,<script>fetch("https://x")</script>',
    'blob:http://127.0.0.1:54321/abc',
    'devtools://devtools/bundled/inspector.html',
    'not a url',
    '',
  ])('cancels %s', (url) => {
    expect(isAllowedRequest(url, policy)).toBe(false);
  });

  it('allows only the exact app-owned files', () => {
    expect(isAllowedRequest('file:///C:/app/dist/error.html', policy)).toBe(true);
    expect(isAllowedRequest('file:///C:/app/dist/error.html?message=boom', policy)).toBe(true);
    expect(isAllowedRequest('file:///C:/Users/me/secret.txt', policy)).toBe(false);
    expect(isAllowedRequest('file:///C:/app/dist/error.html.evil', policy)).toBe(false);
  });

  it('allows nothing before the sidecar has told us its origin', () => {
    const empty: Policy = { allowedOrigins: [], allowedFileUrls: [] };
    expect(isAllowedRequest('http://127.0.0.1:54321/', empty)).toBe(false);
  });

  it('navigation follows the same rule: away from the app is blocked', () => {
    expect(isAllowedNavigation('http://127.0.0.1:54321/#/tanks', policy)).toBe(true);
    expect(isAllowedNavigation('https://example.com', policy)).toBe(false);
  });
});

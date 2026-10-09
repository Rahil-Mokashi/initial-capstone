import { describe, expect, it } from 'vitest';
import { checkInstallPath, MAX_FULL_PATH, tooLongMessage } from './preflight';

const normal = 'C:\\Users\\someone\\AppData\\Local\\PPERP';

describe('install path preflight', () => {
  it('passes a normal per-user install', () => {
    const r = checkInstallPath(normal, 120);
    expect(r.ok).toBe(true);
    expect(r.total).toBe(normal.length + 1 + 120);
  });

  it('ignores a trailing slash', () => {
    expect(checkInstallPath('C:\\PPERP\\', 100).total).toBe(
      checkInstallPath('C:\\PPERP', 100).total,
    );
  });

  it('fails exactly when the total exceeds the limit', () => {
    const dir = 'C:\\' + 'a'.repeat(MAX_FULL_PATH - 100 - 1 - 3);
    expect(checkInstallPath(dir, 100).ok).toBe(true);
    expect(checkInstallPath(dir + 'a', 100).ok).toBe(false);
  });

  it('explains the problem and the fix in plain words, with the real numbers', () => {
    const dir = 'C:\\' + 'x'.repeat(200);
    const msg = tooLongMessage(dir, checkInstallPath(dir, 110));
    expect(msg).toMatch(/too long/);
    expect(msg).toContain(dir);
    expect(msg).toMatch(/at most 129 characters/);
    expect(msg).toContain('C:\\PPERP');
  });
});

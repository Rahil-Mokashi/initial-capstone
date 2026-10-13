import { mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { request } from 'node:http';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { MainPcFixture } from '../e2e/lanFixture';
import {
  type DeviceBundle,
  type SecretBox,
  enrol,
  fetchAuthority,
  forgetBundle,
  groupFingerprint,
  loadBundle,
  normaliseCode,
  parseBundle,
  saveBundle,
  startProxy,
  testConnection,
} from './lan-client';

/** Stand-in for Electron safeStorage: reversible, and it proves the files hold no readable key. */
const box: SecretBox = {
  available: () => true,
  encrypt: (t) => Buffer.from(t, 'utf8').reverse(),
  decrypt: (b) => Buffer.from(b).reverse().toString('utf8'),
};

let dir: string;
let pc: MainPcFixture;

beforeAll(async () => {
  dir = mkdtempSync(join(tmpdir(), 'lan-client-'));
  pc = await MainPcFixture.start(join(dir, 'pc'));
}, 120_000);

afterAll(async () => {
  await pc?.stop();
  rmSync(dir, { recursive: true, force: true });
});

async function pair(name = 'Counter PC'): Promise<DeviceBundle> {
  const { code, fingerprint } = await pc.pair();
  return enrol({ host: pc.ready.host, port: pc.ready.port, pairingPort: pc.ready.pairing_port, code, deviceName: name, confirmedFingerprint: fingerprint });
}

function get(origin: string, path: string, headers: Record<string, string> = {}): Promise<{ status: number; body: string }> {
  return new Promise((resolve, reject) => {
    const url = new URL(path, origin);
    const req = request({ host: url.hostname, port: url.port, path: url.pathname, headers }, (res) => {
      const chunks: Buffer[] = [];
      res.on('data', (c: Buffer) => chunks.push(c));
      res.on('end', () => resolve({ status: res.statusCode ?? 0, body: Buffer.concat(chunks).toString() }));
    });
    req.on('error', reject);
    req.end();
  });
}

describe('pairing', () => {
  it('formats the code and fingerprint the way people read them', () => {
    expect(normaliseCode('k7m2q-9xa4b')).toBe('K7M2Q9XA4B');
    expect(groupFingerprint('abcd1234ef')).toBe('ABCD 1234 EF');
  });

  it('pairs with the right code, and the result can reach the Main PC', async () => {
    const bundle = await pair();
    expect(bundle.token).toHaveLength(64);
    expect((await testConnection(bundle)).ok).toBe(true);
  }, 60_000);

  it('does not pair with a wrong code, and a used code is dead', async () => {
    const { code, fingerprint } = await pc.pair();
    const args = { host: pc.ready.host, port: pc.ready.port, pairingPort: pc.ready.pairing_port, deviceName: 'X PC', confirmedFingerprint: fingerprint };
    await expect(enrol({ ...args, code: 'AAAAA-BBBBB' })).rejects.toThrow(/Pairing failed/);
    await expect(enrol({ ...args, code })).resolves.toBeTruthy();
    await expect(enrol({ ...args, code })).rejects.toThrow();
  }, 60_000);

  it('refuses when the fingerprint is not the one the person confirmed', async () => {
    const { code } = await pc.pair();
    await expect(
      enrol({ host: pc.ready.host, port: pc.ready.port, pairingPort: pc.ready.pairing_port, code, deviceName: 'Y PC', confirmedFingerprint: '0'.repeat(64) }),
    ).rejects.toThrow(/different fingerprint/);
  }, 60_000);

  it('shows the same fingerprint the owner sees', async () => {
    const { fingerprint } = await pc.pair();
    expect((await fetchAuthority(pc.ready.host, pc.ready.pairing_port)).fingerprint).toBe(fingerprint);
  }, 30_000);
});

describe('remembering the device', () => {
  it('keeps no readable key or token on disk and forgets cleanly', async () => {
    const bundle = await pair('Stored PC');
    const store = join(dir, 'user-data');
    saveBundle(store, bundle, box);
    const text = readdirSync(store).map((f) => readFileSync(join(store, f)).toString('latin1')).join('\n');
    expect(text).not.toContain('PRIVATE KEY');
    expect(text).not.toContain(bundle.token);
    expect(loadBundle(store, box)).toEqual(bundle);
    forgetBundle(store);
    expect(loadBundle(store, box)).toBeNull();
  }, 60_000);

  it('refuses to save when the key cannot be protected', async () => {
    const bundle = await pair('Unsafe PC');
    expect(() => saveBundle(join(dir, 'x'), bundle, { ...box, available: () => false })).toThrow(/cannot protect/);
  }, 60_000);

  it('reads a console device file', async () => {
    const file = join(dir, 'main-window.json');
    await pc.local('Main PC window', file);
    const bundle = parseBundle(readFileSync(file, 'utf8'));
    expect((await testConnection(bundle)).ok).toBe(true);
    expect(() => parseBundle('{"host":"x"}')).toThrow(/missing/);
  }, 60_000);
});

describe('test connection', () => {
  it('explains the common failures in plain words', async () => {
    const bundle = await pair('Probe PC');
    expect((await testConnection({ ...bundle, token: '0'.repeat(64) })).message).toMatch(/no longer recognises/);
    expect((await testConnection({ ...bundle, port: 9 })).message).toMatch(/Nothing is listening|did not answer|Could not reach/);
    const stranger = await MainPcFixture.start(join(dir, 'other'));
    try {
      const wrongAuthority = await testConnection({ ...bundle, port: stranger.ready.port });
      expect(wrongAuthority.ok).toBe(false);
      expect(wrongAuthority.message).toMatch(/not the one this PC was paired with|refused the secure connection/);
    } finally {
      await stranger.stop();
    }
  }, 120_000);

  it('notices a device that was removed', async () => {
    const doomed = await pair('Doomed PC');
    const other = await pair('Survivor PC');
    await pc.revoke(doomed.deviceId!);
    expect((await testConnection(doomed)).message).toMatch(/no longer recognises/);
    expect((await testConnection(other)).ok).toBe(true); // a different device stays unaffected
  }, 60_000);
});

describe('the loopback proxy', () => {
  it('forwards the API with the device identity, and demands the launch secret', async () => {
    const bundle = await pair('Proxy PC');
    const proxy = await startProxy(bundle, 'launch-secret');
    try {
      expect((await get(proxy.origin, '/api/health')).status).toBe(403); // no secret
      const ok = await get(proxy.origin, '/api/health', { 'x-launch-secret': 'launch-secret' });
      expect(ok.status).toBe(200);
      expect(JSON.parse(ok.body)).toEqual({ status: 'ok' });
      expect(proxy.status().connected).toBe(true);
      // the Main PC's own sign-in screen data, reached through the proxy
      const device = await get(proxy.origin, '/api/system/device', { 'x-launch-secret': 'launch-secret' });
      expect(JSON.parse(device.body).device).toMatch(/^Proxy PC \(127\.0\.0\.1\)$/);
    } finally {
      await proxy.close();
    }
  }, 60_000);

  it('answers with a plain error, not a hang, when the Main PC cannot be reached', async () => {
    const bundle = await pair('Lonely PC');
    const proxy = await startProxy({ ...bundle, port: 9 }, 's');
    try {
      const reply = await get(proxy.origin, '/api/tanks', { 'x-launch-secret': 's' });
      expect(reply.status).toBe(503);
      expect(JSON.parse(reply.body).error.code).toBe('main_pc_unreachable');
      expect(proxy.status().connected).toBe(false);
      const page = await new Promise<{ status: number; body: string }>((resolve, reject) => {
        const url = new URL(proxy.origin);
        const req = request({ host: url.hostname, port: url.port, path: '/', headers: { accept: 'text/html' } }, (res) => {
          const chunks: Buffer[] = [];
          res.on('data', (c: Buffer) => chunks.push(c));
          res.on('end', () => resolve({ status: res.statusCode ?? 0, body: Buffer.concat(chunks).toString() }));
        });
        req.on('error', reject);
        req.end();
      });
      expect(page.body).toContain('Cannot reach the Main PC');
    } finally {
      await proxy.close();
    }
  }, 60_000);

  it('only answers requests addressed to its own loopback address', async () => {
    const bundle = await pair('Rebind PC');
    const proxy = await startProxy(bundle, 's');
    try {
      const reply = await new Promise<number>((resolve, reject) => {
        const req = request({ host: '127.0.0.1', port: proxy.port, path: '/api/health', headers: { host: 'evil.example', 'x-launch-secret': 's' } }, (res) => {
          res.resume();
          resolve(res.statusCode ?? 0);
        });
        req.on('error', reject);
        req.end();
      });
      expect(reply).toBe(400);
    } finally {
      await proxy.close();
    }
  }, 60_000);
});

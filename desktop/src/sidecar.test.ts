import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import {
  findFreePort,
  newSecret,
  startSidecar,
  stopSidecar,
  waitUntilHealthy,
  type RunningSidecar,
} from './sidecar';

const dirs: string[] = [];
const running: RunningSidecar[] = [];

afterEach(async () => {
  for (const s of running.splice(0)) {
    if (s.child.exitCode === null) s.child.kill('SIGKILL');
    await s.exited;
  }
  for (const d of dirs.splice(0)) rmSync(d, { recursive: true, force: true });
});

/** A stand-in for the Python API: same env contract, same endpoints, tiny. */
function stub(
  behaviour: 'good' | 'ignores-shutdown' | 'dies-at-start' | 'never-healthy',
): string[] {
  const dir = mkdtempSync(join(tmpdir(), 'sidecar-'));
  dirs.push(dir);
  const file = join(dir, 'stub.js');
  writeFileSync(
    file,
    `
const http = require('http');
const behaviour = ${JSON.stringify(behaviour)};
if (behaviour === 'dies-at-start') { console.error('boom: cannot open database'); process.exit(3); }
const server = http.createServer((req, res) => {
  if (req.headers['x-launch-secret'] !== process.env.PPERP_API_SECRET) { res.statusCode = 403; return res.end(); }
  if (req.url === '/api/health') { res.statusCode = behaviour === 'never-healthy' ? 503 : 200; return res.end('{}'); }
  if (req.url === '/api/env') { res.statusCode = 200; return res.end(JSON.stringify({ runAsNode: process.env.ELECTRON_RUN_AS_NODE || null })); }
  if (req.url === '/api/system/shutdown') {
    res.statusCode = 202; res.end('{}');
    if (behaviour === 'good') setTimeout(() => process.exit(0), 50);
    return;
  }
  res.statusCode = 404; res.end();
});
server.listen(Number(process.env.PPERP_API_PORT), '127.0.0.1');
`,
  );
  return [file];
}

async function start(behaviour: Parameters<typeof stub>[0]): Promise<RunningSidecar> {
  const s = await startSidecar({ executable: process.execPath, args: stub(behaviour) });
  running.push(s);
  return s;
}

describe('sidecar helpers', () => {
  it('picks a free loopback port and a long random secret each time', async () => {
    const [a, b] = [await findFreePort(), await findFreePort()];
    expect(a).toBeGreaterThan(1023);
    expect(b).toBeGreaterThan(1023);
    const [s1, s2] = [newSecret(), newSecret()];
    expect(s1).toHaveLength(64);
    expect(s1).not.toBe(s2);
    expect(s1).toMatch(/^[0-9a-f]+$/);
  });

  it('passes port and secret to the child by environment and listens on 127.0.0.1', async () => {
    const s = await start('good');
    expect(s.origin).toBe(`http://127.0.0.1:${s.port}`);
    await waitUntilHealthy(s, 10_000);
    const noSecret = await fetch(`${s.origin}/api/health`);
    expect(noSecret.status).toBe(403);
  });

  it('shuts down gracefully when the API cooperates', async () => {
    const s = await start('good');
    await waitUntilHealthy(s, 10_000);
    expect(await stopSidecar(s, 5000)).toBe('graceful');
    expect(await stopSidecar(s, 100)).toBe('already-stopped');
  });

  it('force-kills only after the timeout when the API ignores the request', async () => {
    const s = await start('ignores-shutdown');
    await waitUntilHealthy(s, 10_000);
    const started = Date.now();
    expect(await stopSidecar(s, 600)).toBe('killed');
    expect(Date.now() - started).toBeGreaterThanOrEqual(550);
  });

  it('reports a crash during startup with the process output', async () => {
    const s = await start('dies-at-start');
    await expect(waitUntilHealthy(s, 10_000)).rejects.toThrow(/cannot open database/);
  });

  it('gives up with a clear message when the API never becomes healthy', async () => {
    const s = await start('never-healthy');
    await expect(waitUntilHealthy(s, 800)).rejects.toThrow(/did not start within/);
  });

  it('does not leak ELECTRON_RUN_AS_NODE into the child', async () => {
    const before = process.env.ELECTRON_RUN_AS_NODE;
    process.env.ELECTRON_RUN_AS_NODE = '1';
    try {
      const s = await start('good');
      await waitUntilHealthy(s, 10_000);
      const seen = await fetch(`${s.origin}/api/env`, {
        headers: { 'X-Launch-Secret': s.secret },
      }).then((r) => r.json());
      expect(seen.runAsNode).toBeNull();
    } finally {
      if (before === undefined) delete process.env.ELECTRON_RUN_AS_NODE;
      else process.env.ELECTRON_RUN_AS_NODE = before;
    }
  });
});

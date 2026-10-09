// Starts, watches and stops the Python API sidecar.
import { type ChildProcess, spawn, spawnSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { createServer } from 'node:net';
import { join } from 'node:path';

export interface SidecarConfig {
  /** Packaged: path to the sidecar executable. Dev: undefined (runs `python -m api.main`). */
  executable?: string;
  /** Arguments for `executable` (the packaged sidecar takes none; tests use a stub script). */
  args?: string[];
  /** Dev: repo root, where `api` is importable. */
  cwd?: string;
  webDir?: string;
  python?: string;
  extraEnv?: NodeJS.ProcessEnv;
}

export interface RunningSidecar {
  port: number;
  secret: string;
  origin: string;
  child: ChildProcess;
  /** Resolves with the exit code when the process ends (for any reason). */
  exited: Promise<number | null>;
  stderrTail(): string;
}

export function findFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      const port = typeof address === 'object' && address ? address.port : 0;
      server.close(() => (port ? resolve(port) : reject(new Error('No free port'))));
    });
  });
}

export const newSecret = (): string => randomBytes(32).toString('hex');

export async function startSidecar(config: SidecarConfig): Promise<RunningSidecar> {
  const port = await findFreePort();
  const secret = newSecret();
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    ...config.extraEnv,
    PPERP_API_PORT: String(port),
    PPERP_API_SECRET: secret,
    PYTHONUNBUFFERED: '1',
    PYTHONUTF8: '1',
  };
  if (config.webDir) env.PPERP_WEB_DIR = config.webDir;
  // Never let a debugging flag from the launching shell turn Electron-in-Node mode on for the child tree.
  delete env.ELECTRON_RUN_AS_NODE;

  const child = config.executable
    ? spawn(config.executable, config.args ?? [], {
        env,
        cwd: join(config.executable, '..'),
        windowsHide: true,
      })
    : spawn(config.python ?? 'python', ['-m', 'api.main'], {
        env,
        cwd: config.cwd,
        windowsHide: true,
      });

  let tail = '';
  const keep = (chunk: Buffer) => {
    tail = (tail + chunk.toString()).slice(-4000);
  };
  child.stderr?.on('data', keep);
  child.stdout?.on('data', keep);

  const exited = new Promise<number | null>((resolve) => {
    child.once('exit', (code) => resolve(code));
    child.once('error', (error) => {
      tail += `\n${error.message}`;
      resolve(-1);
    });
  });

  return {
    port,
    secret,
    origin: `http://127.0.0.1:${port}`,
    child,
    exited,
    stderrTail: () => tail,
  };
}

async function healthy(origin: string, secret: string): Promise<boolean> {
  try {
    const res = await fetch(`${origin}/api/health`, {
      headers: { 'X-Launch-Secret': secret },
      signal: AbortSignal.timeout(1500),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/** Polls the health endpoint until the API answers, the process dies, or the time runs out. */
export async function waitUntilHealthy(sidecar: RunningSidecar, timeoutMs = 90_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let exitedEarly: number | null | undefined;
  void sidecar.exited.then((code) => {
    exitedEarly = code;
  });
  while (Date.now() < deadline) {
    if (exitedEarly !== undefined) {
      throw new Error(
        `The application service stopped while starting (exit code ${exitedEarly}).\n${sidecar.stderrTail()}`,
      );
    }
    if (await healthy(sidecar.origin, sidecar.secret)) return;
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(
    `The application service did not start within ${Math.round(timeoutMs / 1000)} seconds.\n${sidecar.stderrTail()}`,
  );
}

function killTree(sidecar: RunningSidecar): void {
  const pid = sidecar.child.pid;
  if (!pid) return;
  if (process.platform === 'win32')
    spawnSync('taskkill', ['/pid', String(pid), '/T', '/F'], { windowsHide: true });
  else sidecar.child.kill('SIGKILL');
}

/**
 * Graceful first: ask the API to shut down so SQLite checkpoints its WAL file, wait, and only
 * then force-kill the whole process tree.
 */
export async function stopSidecar(
  sidecar: RunningSidecar,
  gracefulMs = 10_000,
): Promise<'graceful' | 'killed' | 'already-stopped'> {
  if (sidecar.child.exitCode !== null || sidecar.child.signalCode !== null)
    return 'already-stopped';
  try {
    await fetch(`${sidecar.origin}/api/system/shutdown`, {
      method: 'POST',
      headers: { 'X-Launch-Secret': sidecar.secret },
      signal: AbortSignal.timeout(3000),
    });
  } catch {
    // The process may already be going away; the wait below decides.
  }
  const winner = await Promise.race([
    sidecar.exited.then(() => 'graceful' as const),
    new Promise<'timeout'>((r) => setTimeout(() => r('timeout'), gracefulMs)),
  ]);
  if (winner === 'graceful') return 'graceful';
  killTree(sidecar);
  await sidecar.exited;
  return 'killed';
}

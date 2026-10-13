// Starts the TEST Main PC (desktop/e2e/lan_main_pc.py): real mutual TLS on 127.0.0.1 with a copy of the seeded database.
import { type ChildProcessWithoutNullStreams, spawn, spawnSync } from 'node:child_process';
import { copyFileSync, mkdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { createInterface } from 'node:readline';

const repoRoot = resolve(__dirname, '..', '..');
const python = process.env.PPERP_PYTHON ?? 'python';

export interface Ready {
  ready: true;
  host: string;
  port: number;
  pairing_port: number;
  fingerprint: string;
}

let template: string | null = null;
/** Seeds one database per test run (same users as the Electron tests: owner1, manager1, ... password Passw0rd!x). */
export function seededTemplate(dir: string): string {
  if (template) return template;
  mkdirSync(dir, { recursive: true });
  const file = join(dir, 'lan-template.db');
  const result = spawnSync(python, ['desktop/e2e/seed_e2e.py'], {
    cwd: repoRoot,
    env: { ...process.env, PETROL_PUMP_DB_PATH: file, PYTHONUTF8: '1' },
    encoding: 'utf8',
  });
  if (result.status !== 0) throw new Error(`seed failed:\n${result.stdout}\n${result.stderr}`);
  template = file;
  return file;
}

export class MainPcFixture {
  private lines: string[] = [];
  private waiting: Array<(line: string) => void> = [];

  private constructor(
    readonly child: ChildProcessWithoutNullStreams,
    readonly ready: Ready,
    readonly dbPath: string,
  ) {}

  static async start(dir: string, opts: { webDir?: string; requestsPerMinute?: number } = {}): Promise<MainPcFixture> {
    mkdirSync(dir, { recursive: true });
    const dbPath = join(dir, 'main-pc.db');
    copyFileSync(seededTemplate(join(dir, '..', 'lan-template')), dbPath);
    const env: NodeJS.ProcessEnv = { ...process.env, PETROL_PUMP_DB_PATH: dbPath, PYTHONUTF8: '1', PYTHONUNBUFFERED: '1' };
    if (opts.webDir) env.PPERP_WEB_DIR = opts.webDir;
    delete env.ELECTRON_RUN_AS_NODE;
    const args = ['desktop/e2e/lan_main_pc.py', '--dir', join(dir, 'lan')];
    if (opts.requestsPerMinute) args.push('--requests-per-minute', String(opts.requestsPerMinute));
    const child = spawn(python, args, { cwd: repoRoot, env, windowsHide: true });
    let stderr = '';
    child.stderr.on('data', (c: Buffer) => (stderr += c.toString()));
    const reader = createInterface({ input: child.stdout });
    const first = await new Promise<string>((res, rej) => {
      const timer = setTimeout(() => rej(new Error(`test Main PC did not start:\n${stderr}`)), 60_000);
      reader.once('line', (l) => {
        clearTimeout(timer);
        res(l);
      });
      child.once('exit', () => rej(new Error(`test Main PC exited:\n${stderr}`)));
    });
    const fixture = new MainPcFixture(child, JSON.parse(first) as Ready, dbPath);
    reader.on('line', (l) => {
      const next = fixture.waiting.shift();
      if (next) next(l);
      else fixture.lines.push(l);
    });
    return fixture;
  }

  private reply(): Promise<Record<string, string>> {
    const queued = this.lines.shift();
    if (queued) return Promise.resolve(JSON.parse(queued));
    return new Promise((res) => this.waiting.push((l) => res(JSON.parse(l))));
  }

  private async command(text: string): Promise<Record<string, string>> {
    this.child.stdin.write(`${text}\n`);
    return this.reply();
  }

  /** The owner pressed "Add a device": a fresh pairing code (single use, 10 minutes). */
  pair(username = 'owner1'): Promise<{ code: string; fingerprint: string }> {
    return this.command(`pair ${username}`) as Promise<{ code: string; fingerprint: string }>;
  }

  /** Console enrolment: writes a device file (the Main PC's own window, or recovery). */
  local(name: string, file: string): Promise<{ device_id: string }> {
    return this.command(`local ${name.replace(/ /g, '_')} ${file}`) as Promise<{ device_id: string }>;
  }

  revoke(deviceId: string): Promise<unknown> {
    return this.command(`revoke ${deviceId}`);
  }

  async stop(): Promise<void> {
    this.child.stdin.write('quit\n');
    await new Promise<void>((res) => {
      const t = setTimeout(() => {
        this.child.kill();
        res();
      }, 8000);
      this.child.once('exit', () => {
        clearTimeout(t);
        res();
      });
    });
  }
}

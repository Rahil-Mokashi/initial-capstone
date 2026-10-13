// Client PC mode: pairing with the Main PC, remembering the device identity, and a loopback proxy.
//
// The window never talks to the network itself. It talks to http://127.0.0.1:<port> exactly as in Single PC mode (so the
// strict CSP and the request blocker are unchanged); this proxy adds the device certificate and token and forwards to the
// Main PC over TLS 1.2+, trusting ONLY the authority received at pairing. See docs/adr-lan-multi-user.md.
import { X509Certificate, createHash, createHmac, pbkdf2Sync, randomBytes, timingSafeEqual } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { type IncomingHttpHeaders, type IncomingMessage, type Server, createServer } from 'node:http';
import { Agent, request as httpsRequest } from 'node:https';
import { join } from 'node:path';

export interface DeviceBundle {
  host: string;
  port: number;
  caPem: string;
  certPem: string;
  keyPem: string;
  token: string;
  deviceName: string;
  /** Known after pairing here; absent in a console device file. */
  deviceId?: string;
}

/** How secrets are kept on disk. Production: Electron safeStorage (Windows DPAPI). Tests: a stand-in. */
export interface SecretBox {
  available(): boolean;
  encrypt(text: string): Buffer;
  decrypt(data: Buffer): string;
}

const PUBLIC_FILE = 'lan-client.json';
const SECRET_FILE = 'lan-client.secret';
const MAX_BODY = 2_000_000;

// ---- pairing -----------------------------------------------------------------------------------------------------------
export const normaliseCode = (code: string): string => code.toUpperCase().replace(/[^A-Z0-9]/g, '');

/** Must match api/lan/devices.py: pairing_key / proof. */
export function pairingKey(code: string): Buffer {
  return pbkdf2Sync(normaliseCode(code), 'pperp-pairing-v1', 200_000, 32, 'sha256');
}

export function proof(key: Buffer, ...parts: string[]): string {
  return createHmac('sha256', key).update(parts.join('|')).digest('hex');
}

export function fingerprintOf(pem: string): string {
  return createHash('sha256').update(new X509Certificate(pem).raw).digest('hex');
}

/** 4F2A 91C0 ... : how a fingerprint is shown to a person comparing two screens. */
export const groupFingerprint = (hex: string): string => (hex.match(/.{1,4}/g) ?? []).join(' ').toUpperCase();

interface JsonReply<T> {
  status: number;
  body: T;
}

function jsonRequest<T>(
  host: string,
  port: number,
  path: string,
  options: { method?: string; body?: unknown; ca?: string; timeoutMs?: number; cert?: string; key?: string; headers?: Record<string, string> },
): Promise<JsonReply<T>> {
  return new Promise((resolve, reject) => {
    const payload = options.body === undefined ? undefined : Buffer.from(JSON.stringify(options.body));
    const req = httpsRequest(
      {
        host,
        port,
        path,
        method: options.method ?? 'GET',
        minVersion: 'TLSv1.2',
        // First contact has no authority yet (rejectUnauthorized false); every later call pins the one we were given.
        ...(options.ca ? { ca: options.ca, rejectUnauthorized: true } : { rejectUnauthorized: false }),
        ...(options.cert ? { cert: options.cert, key: options.key } : {}),
        agent: false,
        timeout: options.timeoutMs ?? 10_000,
        headers: {
          accept: 'application/json',
          ...(payload ? { 'content-type': 'application/json', 'content-length': String(payload.length) } : {}),
          ...options.headers,
        },
      },
      (res) => {
        const chunks: Buffer[] = [];
        res.on('data', (c: Buffer) => chunks.push(c));
        res.on('end', () => {
          const text = Buffer.concat(chunks).toString('utf8');
          try {
            resolve({ status: res.statusCode ?? 0, body: (text ? JSON.parse(text) : {}) as T });
          } catch {
            resolve({ status: res.statusCode ?? 0, body: {} as T });
          }
        });
      },
    );
    req.on('timeout', () => req.destroy(new Error('timeout')));
    req.on('error', reject);
    if (payload) req.write(payload);
    req.end();
  });
}

export interface CaOffer {
  caPem: string;
  fingerprint: string;
}

/** Step 1 of pairing: ask the Main PC for its authority. The person then compares the fingerprint with the owner's screen. */
export async function fetchAuthority(host: string, pairingPort: number): Promise<CaOffer> {
  const { status, body } = await jsonRequest<{ ca_pem?: string; fingerprint?: string }>(host, pairingPort, '/pair/ca', {});
  if (status !== 200 || !body.ca_pem) throw new Error('The Main PC did not offer to pair. Ask the owner to press "Add a device" first.');
  const fingerprint = fingerprintOf(body.ca_pem);
  if (fingerprint !== body.fingerprint) throw new Error('The Main PC sent a certificate that does not match its own fingerprint. Stop and tell the owner.');
  return { caPem: body.ca_pem, fingerprint };
}

/** Step 2: prove we know the code, receive the device certificate and token. The code itself never leaves this PC. */
export async function enrol(args: {
  host: string;
  port: number;
  pairingPort: number;
  code: string;
  deviceName: string;
  confirmedFingerprint: string;
}): Promise<DeviceBundle> {
  const offer = await fetchAuthority(args.host, args.pairingPort);
  if (offer.fingerprint !== args.confirmedFingerprint) {
    throw new Error('The Main PC now shows a different fingerprint than the one you confirmed. Nothing was paired.');
  }
  const key = pairingKey(args.code);
  const nonce = randomBytes(16).toString('hex');
  const name = args.deviceName.trim();
  const reply = await jsonRequest<{
    device_id?: string;
    cert_pem?: string;
    key_pem?: string;
    token?: string;
    server_proof?: string;
  }>(args.host, args.pairingPort, '/pair/enrol', {
    method: 'POST',
    ca: offer.caPem,
    body: { device_name: name, nonce, ca_fingerprint: offer.fingerprint, proof: proof(key, 'enrol', name, nonce, offer.fingerprint) },
  });
  if (reply.status !== 200 || !reply.body.token || !reply.body.cert_pem || !reply.body.key_pem) {
    throw new Error('Pairing failed. Check the code, or ask the owner for a new one (a code works once and lasts 10 minutes).');
  }
  const expected = Buffer.from(proof(key, 'ok', nonce, offer.fingerprint, reply.body.token));
  const got = Buffer.from(String(reply.body.server_proof ?? ''));
  if (expected.length !== got.length || !timingSafeEqual(expected, got)) {
    throw new Error('The Main PC could not prove it knows the pairing code. Nothing was saved.');
  }
  return {
    host: args.host,
    port: args.port,
    caPem: offer.caPem,
    certPem: reply.body.cert_pem,
    keyPem: reply.body.key_pem,
    token: reply.body.token,
    deviceName: name,
    ...(reply.body.device_id ? { deviceId: reply.body.device_id } : {}),
  };
}

/** A bundle written by `pperp_api lan enrol-local` (the Main PC's own window, or recovery). */
export function parseBundle(text: string): DeviceBundle {
  const raw = JSON.parse(text) as Record<string, unknown>;
  const need = (k: string): string => {
    const v = raw[k];
    if (typeof v !== 'string' || !v) throw new Error(`The device file is missing "${k}".`);
    return v;
  };
  return {
    host: need('host'),
    port: Number(raw.port),
    caPem: need('ca_pem'),
    certPem: need('cert_pem'),
    keyPem: need('key_pem'),
    token: need('token'),
    deviceName: need('device_name'),
  };
}

// ---- storing the identity -------------------------------------------------------------------------------------------------
export function saveBundle(dir: string, bundle: DeviceBundle, box: SecretBox): void {
  if (!box.available()) throw new Error('This PC cannot protect the device key (Windows data protection is unavailable); not saved.');
  mkdirSync(dir, { recursive: true });
  const publicPart = { host: bundle.host, port: bundle.port, caPem: bundle.caPem, deviceName: bundle.deviceName, deviceId: bundle.deviceId, fingerprint: fingerprintOf(bundle.caPem) };
  writeFileSync(join(dir, SECRET_FILE), box.encrypt(JSON.stringify({ certPem: bundle.certPem, keyPem: bundle.keyPem, token: bundle.token })));
  writeFileSync(join(dir, PUBLIC_FILE), JSON.stringify(publicPart, null, 2));
}

export function loadBundle(dir: string, box: SecretBox): DeviceBundle | null {
  if (!existsSync(join(dir, PUBLIC_FILE))) return null;
  const { fingerprint: _shownOnly, ...pub } = JSON.parse(readFileSync(join(dir, PUBLIC_FILE), 'utf8')) as Omit<DeviceBundle, 'certPem' | 'keyPem' | 'token'> & { fingerprint?: string };
  void _shownOnly;
  const secret = JSON.parse(box.decrypt(readFileSync(join(dir, SECRET_FILE)))) as Pick<DeviceBundle, 'certPem' | 'keyPem' | 'token'>;
  return { ...pub, ...secret };
}

export function forgetBundle(dir: string): void {
  rmSync(join(dir, PUBLIC_FILE), { force: true });
  rmSync(join(dir, SECRET_FILE), { force: true });
}

export const describeClient = (dir: string): { host: string; port: number; deviceName: string; fingerprint: string } | null => {
  try {
    const pub = JSON.parse(readFileSync(join(dir, PUBLIC_FILE), 'utf8'));
    return { host: pub.host, port: pub.port, deviceName: pub.deviceName, fingerprint: pub.fingerprint };
  } catch {
    return null;
  }
};

// ---- test connection --------------------------------------------------------------------------------------------------------
export interface ConnectionTest {
  ok: boolean;
  ms?: number;
  /** A sentence a shop-floor person can act on. */
  message: string;
}

const TLS_REJECT = /certificate|handshake|alert|ssl|tls|ECONNRESET|socket hang up|EPROTO/i;

export async function testConnection(bundle: DeviceBundle): Promise<ConnectionTest> {
  const started = Date.now();
  try {
    const { status, body } = await jsonRequest<{ error?: { code?: string } }>(bundle.host, bundle.port, '/api/health', {
      ca: bundle.caPem,
      cert: bundle.certPem,
      key: bundle.keyPem,
      headers: { 'x-device-token': bundle.token },
      timeoutMs: 6000,
    });
    const ms = Date.now() - started;
    if (status === 200) return { ok: true, ms, message: `Connected to the Main PC in ${ms} ms.` };
    if (status === 401) return { ok: false, message: 'The Main PC no longer recognises this PC (it was removed). Ask the owner to add it again.' };
    if (status === 403) return { ok: false, message: 'The Main PC refused this network address. Ask the owner to check the allowed networks.' };
    return { ok: false, message: `The Main PC answered with an unexpected reply (${status}${body.error?.code ? ' ' + body.error.code : ''}).` };
  } catch (error) {
    return { ok: false, message: explainNetworkError(error) };
  }
}

export function explainNetworkError(error: unknown): string {
  const code = (error as { code?: string })?.code ?? '';
  const text = error instanceof Error ? error.message : String(error);
  if (code === 'ECONNREFUSED') return 'Nothing is listening at that address and port. Check the Main PC is switched on and the address is right.';
  if (code === 'ETIMEDOUT' || text === 'timeout') return 'The Main PC did not answer in time. Check the network cable or Wi-Fi, and the address.';
  if (code === 'ENOTFOUND' || code === 'EHOSTUNREACH' || code === 'ENETUNREACH') return 'This PC cannot find the Main PC on the network. Check the address and that both are on the same network.';
  if (/self.signed|unable to verify|CERT_|UNABLE_TO|HOSTNAME_MISMATCH|altnames/i.test(code + text)) {
    return 'The Main PC is not the one this PC was paired with (its certificate does not match). Do not continue; tell the owner.';
  }
  if (TLS_REJECT.test(code + text)) return 'The Main PC refused the secure connection. This PC may have been removed; ask the owner to add it again.';
  return `Could not reach the Main PC (${code || text}).`;
}

// ---- the loopback proxy ---------------------------------------------------------------------------------------------------------
export interface ProxyStatus {
  connected: boolean;
  /** Epoch ms of the last answer from the Main PC, or null. */
  lastOk: number | null;
  lastError: string | null;
}

export interface RunningProxy {
  origin: string;
  secret: string;
  port: number;
  status(): ProxyStatus;
  close(): Promise<void>;
}

const HOP = new Set(['connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization', 'te', 'trailer', 'transfer-encoding', 'upgrade', 'host', 'x-launch-secret', 'x-device-token', 'content-length']);

function forwardHeaders(incoming: IncomingHttpHeaders, bundle: DeviceBundle, bodyLength: number): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(incoming)) if (v !== undefined && !HOP.has(k.toLowerCase())) out[k] = Array.isArray(v) ? v.join(', ') : v;
  out.host = `${bundle.host}:${bundle.port}`;
  out['x-device-token'] = bundle.token;
  if (bodyLength > 0) out['content-length'] = String(bodyLength);
  return out;
}

function readBody(req: IncomingMessage): Promise<Buffer | 'too-large'> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    let size = 0;
    req.on('data', (c: Buffer) => {
      size += c.length;
      if (size > MAX_BODY) {
        resolve('too-large');
        req.destroy();
        return;
      }
      chunks.push(c);
    });
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}

const OFFLINE_PAGE = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Petrol Pump ERP</title>
<style>body{font-family:'Segoe UI',system-ui,sans-serif;background:#f4f2ed;color:#1b2420;display:grid;place-items:center;min-height:100vh;margin:0}
main{max-width:520px;padding:32px}h1{font-size:24px;margin:0 0 8px}p{color:#55605a;line-height:1.5}</style></head>
<body><main><h1>Cannot reach the Main PC</h1><p id="why">Trying again every few seconds. Nothing you did is lost: this PC keeps no data of its own.</p>
<p>Check that the Main PC is switched on and that this PC is connected to the pump's network.</p></main>
<script src="/__pperp/offline.js"></script></body></html>`;
const REMOVED_PAGE = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Petrol Pump ERP</title>
<style>body{font-family:'Segoe UI',system-ui,sans-serif;background:#f4f2ed;color:#1b2420;display:grid;place-items:center;min-height:100vh;margin:0}
main{max-width:520px;padding:32px}h1{font-size:24px;margin:0 0 8px}p{color:#55605a;line-height:1.5}</style></head>
<body><main><h1>This PC is not allowed on the Main PC</h1><p>It was removed, or its network address is no longer permitted. Ask the owner to add this PC again from the Devices screen, then open Network setup and pair it.</p></main></body></html>`;
const OFFLINE_JS = `setInterval(async()=>{try{const r=await fetch('/__pperp/ping',{cache:'no-store'});if(r.ok)location.reload()}catch(e){}},3000)`;

export async function startProxy(bundle: DeviceBundle, secret: string, listenPort = 0): Promise<RunningProxy> {
  const agent = new Agent({ ca: bundle.caPem, cert: bundle.certPem, key: bundle.keyPem, minVersion: 'TLSv1.2', keepAlive: true, maxSockets: 16 });
  const state: ProxyStatus = { connected: false, lastOk: null, lastError: null };

  const fail = (res: import('node:http').ServerResponse, status: number, code: string, message: string): void => {
    if (res.headersSent) {
      res.destroy();
      return;
    }
    res.writeHead(status, { 'content-type': 'application/json', 'cache-control': 'no-store' });
    res.end(JSON.stringify({ error: { code, message, details: {} } }));
  };

  let origin = '';
  const server: Server = createServer(async (req, res) => {
    // Only this PC's own window may use the proxy: the address must be ours (defeats DNS rebinding) ...
    if (req.headers.host !== new URL(origin).host) return fail(res, 400, 'bad_host', 'Unexpected host.');
    const url = req.url ?? '/';
    if (url === '/__pperp/offline.js') {
      res.writeHead(200, { 'content-type': 'text/javascript' });
      return void res.end(OFFLINE_JS);
    }
    if (url === '/__pperp/ping') {
      const t = await testConnection(bundle);
      if (!t.ok) return fail(res, 503, 'main_pc_unreachable', t.message);
      res.writeHead(200, { 'content-type': 'application/json', 'cache-control': 'no-store' });
      return void res.end('{"ok":true}');
    }
    if (url === '/__pperp/status') {
      res.writeHead(200, { 'content-type': 'application/json', 'cache-control': 'no-store' });
      return void res.end(JSON.stringify(state));
    }
    // ... and the API additionally needs the per-launch secret, exactly as in Single PC mode.
    if (url.startsWith('/api') && req.headers['x-launch-secret'] !== secret) return fail(res, 403, 'launch_secret_invalid', 'Missing or wrong launch secret.');
    const body = await readBody(req);
    if (body === 'too-large') return fail(res, 413, 'request_too_large', 'That request is too large.');

    const streaming = url.startsWith('/api/events');
    const upstream = httpsRequest(
      { host: bundle.host, port: bundle.port, path: url, method: req.method, headers: forwardHeaders(req.headers, bundle, body.length), agent, timeout: streaming ? 0 : 60_000 },
      (reply) => {
        const wantsPage = String(req.headers.accept ?? '').includes('text/html');
        if (wantsPage && (reply.statusCode === 401 || reply.statusCode === 403)) {
          reply.resume();
          res.writeHead(reply.statusCode, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
          return void res.end(REMOVED_PAGE);
        }
        state.connected = true;
        state.lastOk = Date.now();
        state.lastError = null;
        res.writeHead(reply.statusCode ?? 502, reply.headers);
        reply.pipe(res);
        res.on('close', () => reply.destroy());
      },
    );
    upstream.on('timeout', () => upstream.destroy(new Error('timeout')));
    upstream.on('error', (error) => {
      state.connected = false;
      state.lastError = explainNetworkError(error);
      const wantsPage = String(req.headers.accept ?? '').includes('text/html');
      if (wantsPage && !res.headersSent) {
        res.writeHead(503, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
        return void res.end(OFFLINE_PAGE);
      }
      fail(res, 503, 'main_pc_unreachable', state.lastError);
    });
    if (body.length) upstream.write(body);
    upstream.end();
  });

  await new Promise<void>((resolve, reject) => {
    server.once('error', reject);
    server.listen(listenPort, '127.0.0.1', () => resolve());
  });
  const address = server.address();
  const port = typeof address === 'object' && address ? address.port : 0;
  origin = `http://127.0.0.1:${port}`;
  return {
    origin,
    secret,
    port,
    status: () => ({ ...state }),
    close: () =>
      new Promise<void>((resolve) => {
        agent.destroy();
        server.closeAllConnections();
        server.close(() => resolve());
      }),
  };
}

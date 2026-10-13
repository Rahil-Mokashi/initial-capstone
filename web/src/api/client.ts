import { apiBase, launchSecret } from './bridge';
import { connection, isClient } from './connection';
import { ApiError, networkError, toApiError } from './errors';
import { session } from './session';

type Method = 'GET' | 'POST' | 'PATCH' | 'PUT';

// Two people editing the same record: a read remembers the record's version (the ETag the Main PC sends), and a later
// change to that record sends it back as If-Match. If somebody saved in between the Main PC refuses with "Changed by X at HH:MM".
const versions = new Map<string, string>();
const RECORD = /^\/([a-z][a-z-]*)\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(\/|\?|$)/;
const recordKey = (path: string): string | null => {
  const m = RECORD.exec(path);
  return m ? `/${m[1]}/${m[2]}` : null;
};

async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  const secret = launchSecret();
  if (secret) headers['X-Launch-Secret'] = secret;
  if (session.token) headers.Authorization = `Bearer ${session.token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  const key = recordKey(path);
  if (method !== 'GET' && key && versions.has(key)) headers['If-Match'] = versions.get(key)!;
  // Cannot reach the Main PC: reading what is on screen is fine, saving is not.
  if (method !== 'GET' && isClient() && connection.get().link === 'offline') {
    throw new ApiError(0, 'main_pc_unreachable', 'The Main PC cannot be reached, so nothing can be saved right now. Wait for it to come back, then try again.');
  }

  let res: Response;
  try {
    res = await fetch(`${apiBase()}/api${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    connection.unreachable();
    throw networkError();
  }

  if (!res.ok) {
    const error = await toApiError(res);
    if (error.code === 'main_pc_unreachable') connection.unreachable();
    else connection.answered();
    if (error.isAuthLoss && path !== '/auth/login') session.lost();
    throw error;
  }
  connection.answered();
  if (key && method === 'GET' && path.split('?')[0] === key) {
    const tag = res.headers.get('etag');
    if (tag) versions.set(key, tag);
  } else if (key && method !== 'GET') {
    versions.delete(key); // it changed: the next read brings the new version
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

/** GET a binary file (PDF, Excel, CSV) with the same auth as every other call. */
async function download(path: string): Promise<Blob> {
  const headers: Record<string, string> = {};
  const secret = launchSecret();
  if (secret) headers['X-Launch-Secret'] = secret;
  if (session.token) headers.Authorization = `Bearer ${session.token}`;
  let res: Response;
  try {
    res = await fetch(`${apiBase()}/api${path}`, { headers });
  } catch {
    throw networkError();
  }
  if (!res.ok) {
    const error = await toApiError(res);
    if (error.isAuthLoss) session.lost();
    throw error;
  }
  return res.blob();
}

export const api = {
  download,
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
  patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, body),
  put: <T>(path: string, body: unknown) => request<T>('PUT', path, body),
};

export { ApiError };

import { apiBase, launchSecret } from './bridge';
import { ApiError, networkError, toApiError } from './errors';
import { session } from './session';

type Method = 'GET' | 'POST' | 'PATCH' | 'PUT';

async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  const secret = launchSecret();
  if (secret) headers['X-Launch-Secret'] = secret;
  if (session.token) headers.Authorization = `Bearer ${session.token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  let res: Response;
  try {
    res = await fetch(`${apiBase()}/api${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw networkError();
  }

  if (!res.ok) {
    const error = await toApiError(res);
    if (error.isAuthLoss && path !== '/auth/login') session.lost();
    throw error;
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

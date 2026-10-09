// Offline + navigation policy. Pure functions so they are unit-tested without Electron;
// main.ts wires them into session.webRequest and webContents handlers.

export interface Policy {
  /** Origins the UI may talk to, for example "http://127.0.0.1:54321". */
  allowedOrigins: readonly string[];
  /** Absolute file URLs the app itself owns (the error page). */
  allowedFileUrls: readonly string[];
}

const LOOPBACK = new Set(['127.0.0.1']);

/** True when a request may proceed. Everything else is cancelled by the main process. */
export function isAllowedRequest(rawUrl: string, policy: Policy): boolean {
  let url: URL;
  try {
    url = new URL(rawUrl);
  } catch {
    return false;
  }
  // Credentials in a URL are a classic way to disguise the real host; the app never uses them.
  if (url.username || url.password) return false;
  switch (url.protocol) {
    case 'http:':
      // Loopback only, and only the sidecar's own origin (or the dev server in dev).
      return LOOPBACK.has(url.hostname) && policy.allowedOrigins.includes(url.origin);
    case 'file:':
      return policy.allowedFileUrls.some(
        (allowed) => url.href === allowed || url.href.startsWith(`${allowed}?`),
      );
    case 'devtools:':
    case 'chrome-extension:':
      return false;
    default:
      // https:, ws:, wss:, ftp:, data:, blob: ... nothing else is ever needed.
      return false;
  }
}

/** Navigation is allowed only within the app's own origin. */
export function isAllowedNavigation(rawUrl: string, policy: Policy): boolean {
  return isAllowedRequest(rawUrl, policy);
}

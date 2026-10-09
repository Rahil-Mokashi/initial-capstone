// What the Electron preload exposes (and nothing else). In a plain browser
// (Vite dev, unit tests) the bridge is absent and we fall back to same-origin.
export interface PrintOptions {
  silent?: boolean;
  deviceName?: string;
  pageSize?: 'A4' | { width: number; height: number };
}
export interface PperpBridge {
  apiBase: string;
  launchSecret: string;
  files: { pickPath(): Promise<string | null> };
  print: {
    toPdf(
      html: string,
      options?: PrintOptions,
    ): Promise<{ ok: boolean; path?: string; error?: string }>;
    toPrinter(html: string, options?: PrintOptions): Promise<{ ok: boolean; error?: string }>;
    listPrinters(): Promise<Array<{ name: string; isDefault: boolean }>>;
  };
}

declare global {
  interface Window {
    pperp?: PperpBridge;
  }
}

export function apiBase(): string {
  return window.pperp?.apiBase ?? '';
}

export function launchSecret(): string | undefined {
  return window.pperp?.launchSecret;
}

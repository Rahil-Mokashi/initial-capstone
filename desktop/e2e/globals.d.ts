export {};
declare global {
  interface Window {
    pperp?: {
      apiBase: string;
      launchSecret: string;
      print: { preview(html: string, options?: unknown): Promise<unknown> };
    };
  }
}

// Getting a document out of the app: save an exported file, or open the print preview.
// In the desktop app the person picks where a file goes (the page never chooses a path).
// In a plain browser (dev, unit tests) there is no bridge, so a file is offered as a download.

export interface SaveResult {
  ok: boolean;
  path?: string;
  error?: string;
}

async function toBase64(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

export async function saveFile(name: string, blob: Blob): Promise<SaveResult> {
  const bridge = window.pperp;
  if (bridge) return bridge.files.save(name, await toBase64(blob));
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
  return { ok: true };
}

/** Opens the print-preview window with Print and Save-as-PDF. Desktop app only. */
export async function openPreview(html: string, pageSize?: 'A4'): Promise<SaveResult> {
  const bridge = window.pperp;
  if (!bridge) return { ok: false, error: 'Print preview works in the desktop app only.' };
  const r = await bridge.print.preview(html, pageSize ? { pageSize } : undefined);
  return { ok: r.ok };
}

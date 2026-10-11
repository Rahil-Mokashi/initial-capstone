// The ONLY bridge between the web page and the desktop shell. Everything the page can
// reach is listed here: the API address, the launch secret, and the print helpers.
import { contextBridge, ipcRenderer } from 'electron';

function arg(name: string): string {
  const prefix = `--${name}=`;
  const found = process.argv.find((a) => a.startsWith(prefix));
  return found ? found.slice(prefix.length) : '';
}

interface PrintOptions {
  silent?: boolean;
  deviceName?: string;
  pageSize?: 'A4' | { width: number; height: number };
}

contextBridge.exposeInMainWorld('pperp', {
  apiBase: arg('pperp-api-base'),
  launchSecret: arg('pperp-secret'),
  files: {
    // Opens the Windows file dialog in the main process; the page only ever receives the chosen path (or null).
    pickPath: (): Promise<string | null> => ipcRenderer.invoke('files:pick'),
    // Writes bytes the page already holds (an export) where the PERSON chooses in the Save dialog.
    save: (suggestedName: string, base64: string) =>
      ipcRenderer.invoke('files:save', suggestedName, base64),
  },
  print: {
    toPdf: (html: string, options?: PrintOptions) =>
      ipcRenderer.invoke('print:toPdf', html, options),
    toPrinter: (html: string, options?: PrintOptions) =>
      ipcRenderer.invoke('print:toPrinter', html, options),
    listPrinters: () => ipcRenderer.invoke('print:list'),
    // Opens the print-preview window (paper, zoom, Print, Save as PDF), like Qt's preview dialog.
    preview: (html: string, options?: PrintOptions) => ipcRenderer.invoke('print:preview', html, options),
  },
});

// Printing for the new UI. The renderer sends HTML (a report or a narrow receipt); the main
// process renders it in a hidden, locked-down window and prints it or saves a PDF.
import { BrowserWindow, app, dialog } from 'electron';
import { randomUUID } from 'node:crypto';
import { rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import type { Policy } from './security';

export interface PrintOptions {
  silent?: boolean;
  deviceName?: string;
  /** 'A4', or a custom size in microns (80 mm roll = 80_000 wide). */
  pageSize?: 'A4' | { width: number; height: number };
  /** Where to write the PDF; when omitted a Save dialog asks. */
  outputPath?: string;
}

const MICRONS_PER_INCH = 25_400;

/** Callers give custom sizes in microns (what webContents.print wants); printToPDF wants inches. */
function pdfPageSize(size: PrintOptions['pageSize']): 'A4' | { width: number; height: number } {
  if (!size || size === 'A4') return 'A4';
  return { width: size.width / MICRONS_PER_INCH, height: size.height / MICRONS_PER_INCH };
}

// Document is fully self-contained: no network, no scripts.
const CSP =
  '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:; font-src data:">';

async function withPrintWindow<T>(
  html: string,
  policy: Policy,
  run: (win: BrowserWindow) => Promise<T>,
): Promise<T> {
  const file = join(app.getPath('temp'), `pperp-print-${randomUUID()}.html`);
  writeFileSync(
    file,
    `<!doctype html><html><head><meta charset="utf-8">${CSP}</head><body>${html}</body></html>`,
  );
  const url = pathToFileURL(file).href;
  policy.allowedFileUrls = [...policy.allowedFileUrls, url];
  const win = new BrowserWindow({
    show: false,
    webPreferences: {
      sandbox: true,
      contextIsolation: true,
      nodeIntegration: false,
      javascript: false,
    },
  });
  try {
    await win.loadURL(url);
    return await run(win);
  } finally {
    win.destroy();
    policy.allowedFileUrls = policy.allowedFileUrls.filter((u) => u !== url);
    rmSync(file, { force: true });
  }
}

export async function printToPdf(
  html: string,
  options: PrintOptions,
  policy: Policy,
): Promise<{ ok: boolean; path?: string; error?: string }> {
  try {
    return await withPrintWindow(html, policy, async (win) => {
      const data = await win.webContents.printToPDF({
        pageSize: pdfPageSize(options.pageSize),
        printBackground: true,
        preferCSSPageSize: true,
      });
      // Only the test harness may choose the file; in the real app the user always picks it.
      let path = process.env.PPERP_E2E === '1' ? options.outputPath : undefined;
      if (!path) {
        const choice = await dialog.showSaveDialog({
          defaultPath: join(app.getPath('documents'), 'report.pdf'),
          filters: [{ name: 'PDF', extensions: ['pdf'] }],
        });
        if (choice.canceled || !choice.filePath) return { ok: false, error: 'cancelled' };
        path = choice.filePath;
      }
      writeFileSync(path, data);
      return { ok: true, path };
    });
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

export async function printToPrinter(
  html: string,
  options: PrintOptions,
  policy: Policy,
): Promise<{ ok: boolean; error?: string }> {
  try {
    return await withPrintWindow(
      html,
      policy,
      (win) =>
        new Promise<{ ok: boolean; error?: string }>((resolve) => {
          win.webContents.print(
            {
              silent: options.silent ?? false,
              deviceName: options.deviceName ?? '',
              printBackground: true,
              pageSize: options.pageSize ?? 'A4',
            },
            (success, failureReason) =>
              resolve(
                success ? { ok: true } : { ok: false, error: failureReason || 'print failed' },
              ),
          );
        }),
    );
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

export async function listPrinters(
  win: BrowserWindow,
): Promise<Array<{ name: string; isDefault: boolean }>> {
  const printers = await win.webContents.getPrintersAsync();
  return printers.map((p) => ({
    name: p.name,
    isDefault: Boolean((p as { isDefault?: boolean }).isDefault),
  }));
}

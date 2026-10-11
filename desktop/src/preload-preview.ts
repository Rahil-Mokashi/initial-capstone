// Preload for the print-preview window only. It fills the preview from the document the main
// process holds for this window and wires the toolbar; the page itself is given no API.
import { ipcRenderer } from 'electron';

interface Init {
  html: string;
  pageSize: 'A4' | { width: number; height: number };
}

const MM_TO_PX = 96 / 25.4;
const RECEIPT = { width: 80_000, height: 160_000 }; // microns: 80 x 160 mm

window.addEventListener('DOMContentLoaded', () => {
  void (async () => {
    const init = (await ipcRenderer.invoke('preview:init')) as Init;
    const frame = document.getElementById('doc') as HTMLIFrameElement;
    const sheet = document.getElementById('sheet') as HTMLElement;
    const paper = document.getElementById('paper') as HTMLSelectElement;
    const status = document.getElementById('status') as HTMLElement;
    let zoom = 1;

    // The same page as the print path wraps it in, so what you see is what prints.
    frame.srcdoc = `<!doctype html><html><head><meta charset="utf-8"></head><body>${init.html}</body></html>`;

    const size = () => (paper.value === 'receipt' ? RECEIPT : 'A4');
    const layout = () => {
      const s = size();
      const wmm = s === 'A4' ? 210 : s.width / 1000;
      const hmm = s === 'A4' ? 297 : s.height / 1000;
      sheet.style.width = `${Math.round(wmm * MM_TO_PX)}px`;
      sheet.style.height = `${Math.round(hmm * MM_TO_PX)}px`;
      sheet.style.transform = `scale(${zoom})`;
    };
    if (typeof init.pageSize === 'object') paper.value = 'receipt';
    layout();

    const say = (text: string, error = false) => {
      status.textContent = text;
      status.className = error ? 'error' : '';
    };
    paper.addEventListener('change', layout);
    document.getElementById('zoom-in')?.addEventListener('click', () => {
      zoom = Math.min(2, zoom + 0.25);
      layout();
    });
    document.getElementById('zoom-out')?.addEventListener('click', () => {
      zoom = Math.max(0.5, zoom - 0.25);
      layout();
    });
    document.getElementById('print')?.addEventListener('click', () => {
      void (async () => {
        say('Opening the print dialog...');
        const r = (await ipcRenderer.invoke('print:toPrinter', init.html, { pageSize: size() })) as {
          ok: boolean;
          error?: string;
        };
        say(r.ok ? 'Sent to the printer.' : `Not printed: ${r.error ?? 'cancelled'}`, !r.ok);
      })();
    });
    document.getElementById('pdf')?.addEventListener('click', () => {
      void (async () => {
        const r = (await ipcRenderer.invoke('print:toPdf', init.html, { pageSize: size() })) as {
          ok: boolean;
          path?: string;
          error?: string;
        };
        say(r.ok ? `Saved ${r.path ?? ''}` : `Not saved: ${r.error ?? 'cancelled'}`, !r.ok);
      })();
    });
    document.getElementById('close')?.addEventListener('click', () => window.close());
  })();
});

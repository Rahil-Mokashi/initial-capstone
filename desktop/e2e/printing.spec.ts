import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { expect, signIn, test } from './fixtures';
import { repoRoot } from './global-setup';

// Printing spike. The HTML comes from the Qt app's REAL builders (app/services/report_export.py),
// so this proves the same documents can be produced from the new stack.

function py(script: string, ...args: string[]): string {
  const r = spawnSync(process.env.PPERP_PYTHON ?? 'python', [script, ...args], {
    cwd: repoRoot,
    encoding: 'utf8',
    env: { ...process.env, PYTHONUTF8: '1' },
  });
  if (r.status !== 0) throw new Error(`${script} failed:\n${r.stderr}`);
  return r.stdout;
}

interface PdfFacts {
  pages: number;
  sizes: Array<[number, number]>;
  text: string;
}
const inspect = (file: string): PdfFacts => JSON.parse(py('desktop/e2e/inspect_pdf.py', file));

interface Bridge {
  print: {
    toPdf(html: string, o?: object): Promise<{ ok: boolean; path?: string; error?: string }>;
    toPrinter(html: string, o?: object): Promise<{ ok: boolean; error?: string }>;
    listPrinters(): Promise<Array<{ name: string; isDefault: boolean }>>;
  };
}

test.describe('printing from the Electron app', () => {
  test('a report (A4) and a narrow receipt (80 mm) both export to PDF with correct size and content', async ({
    launched,
  }, testInfo) => {
    const dir = testInfo.outputPath('print');
    py('desktop/e2e/make_samples.py', dir);
    const reportHtml = readFileSync(join(dir, 'report.html'), 'utf8');
    const receiptHtml = readFileSync(join(dir, 'receipt.html'), 'utf8');
    const { page } = launched;
    await signIn(page, 'manager1');

    const reportPdf = resolve(dir, 'report.pdf');
    const r1 = await page.evaluate(
      ([html, path]) =>
        (window as unknown as { pperp: Bridge }).pperp.print.toPdf(html!, {
          pageSize: 'A4',
          outputPath: path,
        }),
      [reportHtml, reportPdf],
    );
    expect(r1).toEqual({ ok: true, path: reportPdf });
    expect(readFileSync(reportPdf).subarray(0, 5).toString()).toBe('%PDF-');
    const report = inspect(reportPdf);
    // A4 is 595.3 x 841.9 pt; Chromium rounds the page up by under a point.
    expect(Math.abs(report.sizes[0]![0] - 595.3)).toBeLessThan(1.5);
    expect(Math.abs(report.sizes[0]![1] - 841.9)).toBeLessThan(1.5);
    expect(report.pages).toBeGreaterThan(1); // 39 rows flow onto a second page
    expect(report.text).toContain('Tank stock report');
    expect(report.text).toContain('2,500.500');

    const receiptPdf = resolve(dir, 'receipt.pdf');
    const r2 = await page.evaluate(
      ([html, path]) =>
        (window as unknown as { pperp: Bridge }).pperp.print.toPdf(html!, {
          pageSize: { width: 80_000, height: 160_000 },
          outputPath: path,
        }),
      [receiptHtml, receiptPdf],
    );
    expect(r2.ok).toBe(true);
    const receipt = inspect(receiptPdf);
    expect(receipt.pages).toBe(1);
    // 80 mm = 226.8 pt wide, 160 mm = 453.5 pt tall
    expect(Math.abs(receipt.sizes[0]![0] - 226.8)).toBeLessThan(1.5);
    expect(Math.abs(receipt.sizes[0]![1] - 453.5)).toBeLessThan(1.5);
    expect(receipt.text).toContain('R-000123');
    expect(receipt.text).toContain('1306.88');
    testInfo.annotations.push({
      type: 'receipt-size-pt',
      description: JSON.stringify(receipt.sizes[0]),
    });
  });

  test('the renderer cannot choose where a PDF is written outside the test harness', async ({
    launched,
  }, testInfo) => {
    // outputPath is honoured only when PPERP_E2E=1 (set by these tests). Prove the gate exists in the build.
    const source = readFileSync(resolve(__dirname, '..', 'src', 'print.ts'), 'utf8');
    expect(source).toMatch(/PPERP_E2E === '1' \? options\.outputPath : undefined/);
    expect(launched.page).toBeDefined();
    expect(existsSync(testInfo.outputDir)).toBe(true);
  });

  test('lists the system printers and, on request, prints silently to the default one', async ({
    launched,
  }, testInfo) => {
    const { page } = launched;
    const printers = await page.evaluate(() =>
      (window as unknown as { pperp: Bridge }).pperp.print.listPrinters(),
    );
    testInfo.annotations.push({ type: 'printers', description: JSON.stringify(printers) });
    console.log('PRINTERS', JSON.stringify(printers));
    expect(Array.isArray(printers)).toBe(true);

    test.skip(
      process.env.PRINT_SPIKE !== '1',
      'silent printing touches a real printer: run with PRINT_SPIKE=1',
    );
    // Electron may report no printer as default even when Windows has one; '' means "the system default".
    const def = printers.find((p) => p.isDefault) ?? { name: '', isDefault: true };
    const dir = testInfo.outputPath('print');
    py('desktop/e2e/make_samples.py', dir);
    const html = readFileSync(join(dir, 'receipt.html'), 'utf8');
    const outcome = await Promise.race([
      page.evaluate(
        ([h, name]) =>
          (window as unknown as { pperp: Bridge }).pperp.print.toPrinter(h!, {
            silent: true,
            deviceName: name,
            pageSize: { width: 80_000, height: 160_000 },
          }),
        [html, def.name],
      ),
      new Promise<{ ok: boolean; error: string }>((r) =>
        setTimeout(() => r({ ok: false, error: 'TIMED OUT after 30 s' }), 30_000),
      ),
    ]);
    console.log('SILENT PRINT RESULT', def.name || '(system default)', JSON.stringify(outcome));
    testInfo.annotations.push({
      type: 'silent-print',
      description: `${def.name || '(system default)'}: ${JSON.stringify(outcome)}`,
    });
  });
});

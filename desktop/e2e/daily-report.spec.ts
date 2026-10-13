import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, signIn, test } from './fixtures';
import { repoRoot } from './global-setup';

// The daily report is built in Python and printed by the desktop shell's existing HTML-to-PDF path.
// This builds a synthetic day (tests/api/pump_day.py), prints the real HTML in Chromium and inspects the PDF.

function py(args: string[], env: Record<string, string> = {}): string {
  const r = spawnSync(process.env.PPERP_PYTHON ?? 'python', args, {
    cwd: repoRoot,
    encoding: 'utf8',
    env: { ...process.env, PYTHONUTF8: '1', ...env },
  });
  if (r.status !== 0) throw new Error(`${args.join(' ')} failed:\n${r.stdout}\n${r.stderr}`);
  return r.stdout;
}

interface Bridge {
  print: {
    toPdf(html: string, o?: object): Promise<{ ok: boolean; path?: string; error?: string }>;
  };
}

for (const style of ['classic', 'plus'] as const)
  test(`the ${style} daily report prints to exactly two A4 sides with the old report sections`, async ({
    launched,
  }, testInfo) => {
    const html = testInfo.outputPath('daily-report.html');
    py(
      [
        '-m',
        'pytest',
        'tests/api/test_api_daily_report.py',
        '-k',
        'export_html',
        '-q',
        '-p',
        'no:cacheprovider',
      ],
      { PPERP_REPORT_HTML_OUT: html, PPERP_REPORT_STYLE: style },
    );
    expect(existsSync(html)).toBe(true);

    const { page } = launched;
    await signIn(page, 'manager1');
    const pdf = resolve(testInfo.outputPath('daily-report.pdf'));
    const result = await page.evaluate(
      ([h, path]) =>
        (window as unknown as { pperp: Bridge }).pperp.print.toPdf(h!, {
          pageSize: 'A4',
          outputPath: path,
        }),
      [readFileSync(html, 'utf8'), pdf],
    );
    expect(result).toEqual({ ok: true, path: pdf });

    const facts = JSON.parse(py(['desktop/e2e/inspect_pdf.py', pdf])) as {
      pages: number;
      sizes: Array<[number, number]>;
      text: string;
    };
    expect(facts.pages).toBe(2); // front and back of one sheet
    for (const size of facts.sizes) {
      expect(Math.abs(size[0] - 595.3)).toBeLessThan(1.5);
      expect(Math.abs(size[1] - 841.9)).toBeLessThan(1.5);
    }
    for (const text of [
      'Sale Details',
      'MS-22',
      'HSD-22',
      'Total Stock',
      'Total Rs',
      'Shift 1 Transaction Details',
      'DTP Card',
      'PHONE PAY',
      'PTM',
      'Shift 1 Cash Book',
      'Cash in hand',
      'Shift 1 Credit Sale',
      'Stock Transfer (Bouser)',
      'Expenses Details',
      'Oil Sale',
      'Bowser Van',
      'Net Sale',
      style === 'plus' ? '2,30,500.00' : '2,30,500.00',
    ]) {
      expect(facts.text, text).toContain(text);
    }
    // the front side holds the sale details and cash books; the back side starts at Expenses Details
    const [front, back] = facts.text.split('Expenses Details');
    expect(front).toContain('Shift 2 Credit Sale');
    expect(back).toContain('Bowser Van');
  });

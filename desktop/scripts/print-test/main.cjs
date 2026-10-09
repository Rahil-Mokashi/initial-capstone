/* eslint-disable @typescript-eslint/no-require-imports -- plain Electron script */
// Manual printing test. It prints two sample documents, the A4 report and the 80 mm receipt (the same
// HTML the Qt app builds), to a printer you choose BY NAME, and records exactly what Electron answered.
// It proves nothing by itself: a person has to look at the paper. See PRINTING_TEST.md.
//
// Options:
//   --list                    list the installed printers and exit
//   --printer "<name>"        printer to use (exact name from --list). Omit to use the system default.
//   --doc report|receipt|both which sample(s) to print (default both)
//   --dialog                  show the print dialog instead of printing silently
//   --receipt-width-mm <n>    paper width for the receipt (default 80)
//   --receipt-height-mm <n>   page height for the receipt (default 160; use a long page such as 400 on a roll)
//   --margins none|default    page margins (default none for the receipt, default for the report)
//   --to-pdf <folder>         NO printer: write the two PDFs to a folder instead (to check the documents load)
const { BrowserWindow, app } = require('electron');
const { appendFileSync, mkdirSync, writeFileSync } = require('node:fs');
const { join, resolve } = require('node:path');
const { pathToFileURL } = require('node:url');

function arg(name, fallback) {
  const i = process.argv.indexOf('--' + name);
  if (i === -1) return fallback;
  const next = process.argv[i + 1];
  return next === undefined || next.startsWith('--') ? true : next;
}

const logFile = resolve(process.cwd(), 'print-test-log.txt');
function log(line) {
  const text = new Date().toISOString() + '  ' + line;
  console.log(text);
  appendFileSync(logFile, text + '\n');
}

// Without this handler Electron quits as soon as the last (hidden) window closes, between two jobs.
app.on('window-all-closed', () => {});

async function main() {
  writeFileSync(logFile, '');
  log('print-test starting. Electron ' + process.versions.electron + ', log file ' + logFile);

  const host = new BrowserWindow({ show: false });
  const printers = await host.webContents.getPrintersAsync();
  host.destroy();

  if (arg('list', false)) {
    log('Installed printers (' + printers.length + '):');
    for (const p of printers) {
      log(
        '  - "' +
          p.name +
          '"  default=' +
          Boolean(p.isDefault) +
          '  status=' +
          p.status +
          '  description=' +
          (p.description || ''),
      );
    }
    log('Pass one of the names above with --printer "<name>". Nothing was printed.');
    return app.exit(0);
  }

  const printer = arg('printer', '');
  if (printer && printer !== true && !printers.some((p) => p.name === printer)) {
    log('ERROR: no printer named "' + printer + '". Use --list to see the exact names.');
    return app.exit(2);
  }
  const deviceName = printer === true ? '' : printer;
  const which = arg('doc', 'both');
  const silent = !arg('dialog', false);
  const toPdf = arg('to-pdf', false);
  const widthMm = Number(arg('receipt-width-mm', 80));
  const heightMm = Number(arg('receipt-height-mm', 160));
  const margins = arg('margins', null);

  const jobs = [];
  if (which === 'report' || which === 'both') {
    jobs.push({
      name: 'A4 report',
      file: 'report.html',
      pageSize: 'A4',
      pdfSize: 'A4',
      margin: margins === 'none' ? 'none' : 'default',
    });
  }
  if (which === 'receipt' || which === 'both') {
    jobs.push({
      name: widthMm + ' mm receipt',
      file: 'receipt.html',
      pageSize: { width: widthMm * 1000, height: heightMm * 1000 }, // microns, as webContents.print wants
      pdfSize: { width: widthMm / 25.4, height: heightMm / 25.4 }, // inches, as printToPDF wants
      margin: margins === 'default' ? 'default' : 'none',
    });
  }

  log(
    'Target: ' +
      (toPdf
        ? 'PDF files in ' + toPdf
        : deviceName
          ? '"' + deviceName + '"'
          : '(system default printer)') +
      ', silent=' +
      silent,
  );
  let failed = 0;

  for (const job of jobs) {
    const win = new BrowserWindow({ show: false, webPreferences: { sandbox: true } });
    await win.loadURL(pathToFileURL(join(__dirname, job.file)).href);
    // The page size comes from the options above, not from the document, so you can try other widths.
    await win.webContents.insertCSS(
      job.file === 'receipt.html'
        ? '@page { size: ' + widthMm + 'mm ' + heightMm + 'mm; margin: 0 }'
        : '@page { size: A4; margin: 12mm }',
    );
    const started = Date.now();
    log('Job "' + job.name + '": sending...');
    if (toPdf) {
      mkdirSync(resolve(toPdf), { recursive: true });
      const data = await win.webContents.printToPDF({
        pageSize: job.pdfSize,
        printBackground: true,
        preferCSSPageSize: true,
      });
      const out = resolve(toPdf, job.file.replace('.html', '.pdf'));
      writeFileSync(out, data);
      log('Job "' + job.name + '": wrote ' + out + ' (' + data.length + ' bytes)');
    } else {
      const result = await new Promise((done) => {
        win.webContents.print(
          {
            silent,
            deviceName,
            printBackground: true,
            pageSize: job.pageSize,
            margins: { marginType: job.margin },
          },
          (success, failureReason) => done({ success, failureReason }),
        );
      });
      // "success: true" only means the job was handed to the Windows spooler. Check the paper.
      log(
        'Job "' +
          job.name +
          '": callback success=' +
          result.success +
          ' failureReason="' +
          (result.failureReason || '') +
          '" after ' +
          (Date.now() - started) +
          ' ms',
      );
      if (!result.success) failed += 1;
    }
    win.destroy();
  }

  log(
    failed
      ? 'FINISHED with ' + failed + ' failed job(s).'
      : 'FINISHED. A success line above means "handed to the spooler", NOT "printed correctly": look at the paper.',
  );
  app.exit(failed ? 1 : 0);
}

app
  .whenReady()
  .then(main)
  .catch((error) => {
    log('ERROR: ' + (error && error.stack ? error.stack : error));
    app.exit(3);
  });

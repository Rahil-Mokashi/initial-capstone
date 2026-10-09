# Printing test (for a real printer)

**Status: printing from the new app is UNVERIFIED on real hardware.**
What has been checked, on a PC with only "Microsoft Print to PDF" and "OneNote": the sample A4 report and the
80 mm receipt are produced correctly as PDF files (right page size, all text present). A silent print to the
"Microsoft Print to PDF" driver reported success but produced no file, because that driver always asks for a file
name, so it proves nothing. **Nothing has been printed on paper.** This page is how you check that.

The test prints the same two documents the Qt app prints (the report HTML and the sale-receipt HTML), so what
you see on paper is what the new app will produce.

## What you need
- The repo on a PC that has the printer installed in Windows (Settings, Printers & scanners).
- Node.js 22 and the desktop dependencies: open a terminal in the `desktop` folder and run `npm install` once.
- In PowerShell, clear this variable if your terminal sets it (some do): `Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue`

## Steps
1. List the printers Windows knows about, and copy the exact name of yours:
   ```
   npm run print-test -- --list
   ```
2. Check the documents without paper (writes two PDFs, no printer involved):
   ```
   npm run print-test -- --to-pdf C:\temp\print-check
   ```
   Open `report.pdf` and `receipt.pdf`; they should look right.
3. Print the A4 report and the 80 mm receipt to your printer (replace the name):
   ```
   npm run print-test -- --printer "EPSON TM-T82 Receipt" --doc both
   ```
   Useful options: `--doc report` or `--doc receipt` to print one; `--dialog` to show the Windows print dialog
   instead of printing silently; `--receipt-width-mm 58` for a 58 mm roll; `--receipt-height-mm 400` for a long
   page; `--margins none` or `--margins default`.
   Leave out `--printer` to use the Windows default printer.
4. Every run writes `print-test-log.txt` in the folder you ran it from. It records the printer, the options, and
   exactly what Windows answered for each job (`success=true/false` and the failure reason). **`success=true` only
   means the job was handed to the print spooler, not that the paper is right.** Look at the paper.
5. Send me (or keep with your notes) the log file and a photo of the paper.

## Checklist: A4 report on a normal printer
- [ ] Prints on one run without any dialog (silent), or the dialog appears if `--dialog` was used
- [ ] Two pages for the sample report (39 rows)
- [ ] Heading "Petrol Pump ERP" and "Tank stock report" present, table borders visible
- [ ] Nothing cut off at the right or bottom edge
- [ ] Digits are correct (for example 2,500.500)

## Checklist: thermal receipt printer (58 / 80 mm)
Fill in as you go; any "No" is a finding, not a failure of you.
- [ ] **Driver or raw?** Which is installed: a Windows driver for the model (Epson, TVS, etc.), or "Generic / Text only"? Write it down.
  The test above only exercises the Windows driver route (the page is drawn like any other document).
- [ ] **Page size:** in Printer preferences, is the paper size the roll width (80 mm or 58 mm) and the length "roll / continuous"? If the receipt prints on a tall blank page, set the length or run with `--receipt-height-mm`.
- [ ] **Width:** does the text use the full printable width, with no word cut at the right edge? (Typical printable width: 72 mm on 80 mm paper, 48 mm on 58 mm paper.)
- [ ] **Margins:** with `--margins none`, is the left edge clean? If something is cut, try `--margins default`.
- [ ] **Length:** does the paper stop right after the last line, or is there a long blank tail?
- [ ] **Cut:** does the cutter operate after the receipt? (Many drivers have a "cut after document" setting.) Yes / No / Setting found: ____
- [ ] **Density / darkness:** is the print dark enough and the dotted lines readable? Setting changed: ____
- [ ] **Speed:** seconds from sending to paper: ____
- [ ] **Cash drawer:** does the drawer kick (if connected)? A driver-printed page does not send the drawer pulse; this needs raw ESC/POS output (see below). Yes / No
- [ ] **Rupee sign and Hindi/Marathi text** (if used): do they print, or appear as boxes? Yes / No

## If the driver route is not enough
Cutting, drawer kick and fast text receipts usually need **raw ESC/POS output** written straight to the printer
(a small Node module, or a Windows RAW print queue). That is not built yet. The Chromium print path used here cannot
send those commands. If your checklist shows cut or drawer failing, tell me and that becomes a separate, small task.

## Known limits of this test
- It cannot judge print quality; only a person looking at the paper can.
- Electron reports no printer as "default" on the test PC even though Windows has one, so pass `--printer` by name.
- A 58 mm roll needs `--receipt-width-mm 58`; the sample receipt layout was designed for 80 mm.

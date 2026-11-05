# Twelve-hour build report

Branch `feature/site-visit-build` (never pushed; only new commits on top of `reset/pre-12h-2026-10-12`). Full running detail and every
judgment call: `docs/history/TWELVE_HOUR_LOG.md`. Written for: the developer and the pump owners' representative reading what was built.

**Start 23:42 on 12 Oct, report written at the end of the work. About 9 hours of wall clock were used; the session sat idle for
roughly five hours in the middle, so the build stopped well inside the 12 hours. I stopped when the report was written.**

## Per track

| Track | Status | Commits |
|---|---|---|
| 0 Preflight, reset point | **Done.** Fix batch was already done (report existed). Found and fixed a date-fragile test. | `c299f3e`, `923fd87`, `6c49542`, `5c42890` |
| 1 Checks engine, roles, role-based Today | **Done.** `DATA_ENTRY` added (ACCOUNTANT already existed). | `f287077`, `8906e56` (see finding), `524290d` |
| 2 Daily report, Classic | **Done**, except the PRIVATE regression test could only be written to skip (no `private_samples/` on this machine). | `679b08b` (gap analysis), `2251ba0` |
| 3 Credit and recovery | **Done.** | `6b561fa` |
| 4 Bank reconciliation | **Done**, not verified against a real bank file. | `e5ea510` |
| 5 Accounts login, payroll | **Done** (Excel import deferred by design, U-02). | `e5ea510` |
| 6 Daily report, Plus | **Done** (both styles verified as exactly two A4 pages in Chromium). | `e5ea510` |
| Extra: Shift Close entry | **Done**, added after the owner's correction about how data is really entered. | last commit |
| 7 Wrap-up | This report. | |

Tracks 4, 5 and 6 are one commit on purpose (shared files, one full green run): see the log.

### Finding worth knowing first
`web/src/lib/` (20 files every screen imports) had **never been committed**: a generic `lib/` ignore rule hid it. A fresh clone of
`feature/js-frontend` could not build the UI. Fixed in `8906e56`.

## Test counts

| Suite | Before (baseline) | After |
|---|---|---|
| Python | 1523 passed | **1804 passed, 1 skipped** |
| Web Vitest | 317 | **360** |
| Desktop Vitest | 33 | **33** |
| Playwright | 46 passed, 8 opt-in skipped | **53 passed**, 9 opt-in skipped (includes the screenshots spec) |

Python had no hang this time. One web test (reconciliation approve) failed once while the machine was busy and passes alone.

## Screenshots (synthetic data only)
`docs/screenshots/12h/`: `today-owner.png`, `today-data-entry.png`, `checks.png`, `daily-report-classic.png`, `daily-report-plus.png`,
`daily-report-screen.png`, `credit-customer.png`, `credit-ageing.png`, `bank-matching.png`, `payroll-register.png`.
Regenerate: `SCREENSHOTS=1 npx playwright test e2e/screenshots-12h.spec.ts` in `desktop/` (seeds `e2e/seed_demo_day.py`).

## Five-minute demos (all on the synthetic demo database)
Make it: `PETROL_PUMP_DB_PATH=<new file> python desktop/e2e/seed_demo_day.py`, point the app at it, passwords are `Passw0rd!x`
for `owner1`, `manager1`, `accountant1`, `dataentry1`, `admin1`.
1. **Checks** (owner1): Today shows "N of M checks passed"; open Checks: failures first, each with the two figures and a link to the records; add an explanation and see it can't change the result.
2. **Classic report** (manager1): Daily Report, pick the day, Print preview: two sides, same sections as the old report. Compare Shift 1 total with Total Sale. Retype a PTM total on "Card / Phone Pay totals" and watch the check fail.
3. **Plus report**: same page, Style = Plus; Finalise this day; change a figure and see "figures have changed since".
4. **Credit** (owner1): Credit Ageing; open a customer; try a credit sale past the limit on the Terminal: it stops, an owner types their own password to allow it, and it shows on the customer page. Log a follow-up with a promise: it appears under "To chase today".
5. **Bank** (accountant1): Bank Matching; Import a statement (CSV), preview, import twice (nothing is added twice); "Check the books against the bank"; confirm the batch suggestion; mark the stray credit "not the pump's".
6. **Payroll** (accountant1 prepares, owner1 approves): set salaries, give an advance, prepare last month, set deductions, owner approves, mark paid (cash or bank), open a payslip; see the tallies under Checks.
7. **Shift Close** (dataentry1): type the closing readings of a shift.

## OPEN QUESTIONS FOR THE OWNER (with the default used meanwhile)
**Daily report**
- T-01 Are shift litres already net of testing? Default: testing shown, not added back.
- T-02 Allowed gap between dip and book stock. Default 0.5 %.
- T-03 / T-04 How halves are rounded, per bill or on totals. Default: each bill to paise, ROUND_HALF_UP, totals add rounded bills.
- T-06 Exactly what Advance and Final mean. Default: typed cash collections on the shift cash book.
- T-12 Should internal fuel (own vehicles, genset) also reduce tank stock? Default no (it already passes the meters).
- T-13 How the bowser's opening stock is valued in rupees. Default: yesterday's closing litres at weighted-average cost.
- T-14 Do not-yet-approved expenses belong on the printed report? Default: yes, a check warns until approved.
- V-18 Which product (incl. Power) is in MS-22 / MS-16? Not needed by the report (labels are tank names).
- Q3 What DTP Card is. Q7 Is the bill-number series shared across shifts and days? Default: the app's receipt number is printed.
- The old report's Shift 1 figures contain a 0.227 gap and an expense total that may be a misread digit: the app cannot reproduce either by design; confirm with the owner.
**People and roles**
- V-01 / V-02 The order the paper bundle arrives in. Default: credit bills, closing readings, payment-mode totals, expenses, oil, bowser, Advance/Final/deposits.
- V-03 / V-04 Exactly what the cashier role may do. Default: `DATA_ENTRY` (shift, sale, expense, reconciliation entry; no approvals, users, prices, attendance).
- U-08 / U-09 Accountant's access. Default: payroll, expenses, bank matching, credit view and recovery, daily report; cash book view only.
**Credit**
- V-14 Over the limit: warn (owner can allow) or block. Default warn.
- V-10 Do new credit customers need an owner's approval? Default no (recorded as approved by whoever opened the account).
- J-05 Which bills carry vehicle / slip numbers. Default: bowser bills always, credit sales on request.
**Bank**
- H-02 Which payment mode lands in which account (a setting per account). H-09 Bank charge tolerance, default 2 %; date window default 4 days.
- H-24 Who may use bank matching. Default: accountant and owners. H-25 Owner lock on confirmed matches: built. H-07 PDF statements: out of scope.
**Payroll**
- U-04 Salary rules. Default: prorated by days present, leave and holidays unpaid, deductions typed. U-02 The Excel files (import deferred).
- How shortage recoveries through salary should post into the existing shortage ledger.
**Site**
- Nozzles: the notes say 4 nozzles on each of 3 dispensers; the app's confirmed rule is exactly 2 per dispenser. Not changed (see below).

## NEEDS HUMAN REVIEW
1. **Nozzle cap.** `MAX_NOZZLES_PER_DISPENSER = 2` (decided 2026-08-15) contradicts "3 dispensers x 4 nozzles". Workaround: one dispenser per physical face. Owner must decide.
2. **`CreditService.limit_override`**: the one additive change to an existing service (one `if`, off unless an owner re-entered their password). A cleaner hook may be preferred.
3. **Shift Close stand-in employees**: the existing model requires an employee on every nozzle assignment, so each nozzle gets one stand-in record `NOZZLE-<code>` ("Nozzle N1 (shift entry)"), visible in the Employees list. Dropping the employee requirement would change existing models.
4. **DATA_ENTRY role** permissions (V-03, V-04) and the **ACCOUNTANT** additions (U-08, U-09, H-24) are defaults the owners must confirm. New permissions are listed in `PROJECT_CONTEXT.md`.
5. **Shortage recovery through salary** is checked against the shortage records but not posted into them.
6. A pre-existing prettier drift in `web/src/api/bridge.ts`, `client.ts`, `test/mockApi.ts` was left alone.

## Not verified here
- **The PRIVATE regression** against the owner's real figures: `private_samples/` does not exist on this machine. The checker logic is proven on synthetic sheets (`tests/private/`); a photo of the real report was shared in the chat but deliberately not copied into the repo.
- Real bank statement layouts and real UPI/UTR narrations (parser tested on synthetic CSV/XLSX).
- Printing on a real printer; the installed app running offline (`docs/OFFLINE_ACCEPTANCE.md` steps still apply); the installer/sidecar were not rebuilt (the Qt exe is unchanged; **`dist/PetrolPumpERP.exe` is Qt and does not include any of this**).
- Behaviour with more than two shifts in a day (data is kept; the printout shows the first two).
- Real attendance data feeding payroll (tested on synthetic attendance).

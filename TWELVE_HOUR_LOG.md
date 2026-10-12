# Twelve-hour site-visit build log

**Started: 2026-10-12 23:42 (local, IST).** Branch for the work: `feature/site-visit-build` (created in Track 0).
Source brief: `PROMPT_12H.md` (gitignored). Restart rule: read this file, continue from the first unfinished step.

## Preflight findings (Track 0)
- `SITE_NOTES.md`, `PROMPT_12H.md`, `run_12h.ps1`, `private_samples/` were **not on disk** at start. The brief and notes arrived as pasted text (the notes paste was cut off after "Hard requirements"); I saved both as gitignored files. **No private figures or photos exist on this machine**, so the PRIVATE regression test (Track 2) can only be written to skip cleanly; the formulas come from the brief and `docs/daily-report-spec.md`.
- `OWNER_ANSWERS.md`, `SECURITY_REPORT.md`, `FIX_BATCH_PROMPT.md`: absent. `FIX_BATCH_REPORT.md` present, so the fix batch is not pending.
- Working tree was clean; started on `feature/js-frontend`.
- Commit 1: `.gitignore` now covers the four private inputs. `git ls-files` shows none tracked.
- Baseline run found a date-fragile test (`tests/api` hard-coded `shift_date` 2026-10-11, which was "today" only yesterday): fixed to use today's date.
- Existing code already has: `ACCOUNTANT` role, 8 seeded `Tender`s (Cash, Credit, Card, DTP Card, PhonePe, Paytm, Expenses, Other), `ShiftCashBook` (Advance/Final), `ShiftBankDeposit`, shortage recoveries, credit accounts. The brief says "add the role ACCOUNTANT"; it already exists, so I only add new permissions to it.

## Track 0 result (done by 00:20, elapsed 0h38)
- Commits: `c299f3e` gitignore, `923fd87` test date fix, `6c49542` RESET_POINT. Tag `reset/pre-12h-2026-10-12` -> `923fd87`. Bundle `..\PetrolPumpERP-pre-12h-2026-10-12.bundle` verified okay (14.9 MB). Branch `feature/site-visit-build`.
- **Baseline counts** (before): Python **1523** passed (18m17s, no hang; before the date fix 1 test failed); web Vitest **317**; desktop Vitest **33**; Playwright **46** passed, 8 opt-in skipped.
- Judgment: the full Python suite takes ~18 min, so I run targeted tests per step and the full suites once at the end of each track.

## Track 1 (started 00:20, elapsed since 23:42: 0h38; real clock times, an earlier draft of this line was wrong)
### Commit: checks engine, owner settings, DATA_ENTRY role
- Added: `CheckResult`/`CheckExplanation` (append-only), `PumpSetting` key-value table with a registry of owner decisions (`rounding_rule` T-03/T-04, `add_testing_back` T-01, `internal_fuel_deducts_tank` T-12, `credit_over_limit` V-14, `daily_report_style`, `dip_tolerance_percent` T-02, bank tolerance/window H-09/H-02, `new_customer_approval` V-10), `CheckService`, role `DATA_ENTRY`, permissions `check.view`/`check.explain`, one Alembic migration (`3c4f91bf20be`), and a test that fails if models and migrations ever disagree.
- Tests: new `tests/site` = 17 passed. (Suite-wide counts at the end of the track.)
- Judgment calls:
  - **ACCOUNTANT already existed**, so nothing was added; it (and MANAGER) gained `check.view`/`check.explain` only. OWNER/ADMIN get every permission automatically.
  - **DATA_ENTRY added** (SHIFT_SUPERVISOR carries attendance/leave management, wrong for a cashier). Permissions: shift/sale/expense/reconciliation view+manage, credit view, inventory/nozzle/fuel-price/employee/settings view. No approvals, no users, no prices, no shortage booking. **NEEDS HUMAN REVIEW (V-03, V-04).**
  - Several OWNER logins already work (any number of users per role); a test pins it. Approvals already record the acting user.
  - Settings live in a new table instead of new columns on `AppSetting`, so the existing model and migrations stay untouched.
  - A check with a missing side (expected or actual unknown) is a FAIL, never a pass.

### Commit: web/src/lib was never tracked (found while splitting commits)
- **Finding (important):** `.gitignore` line 17 is the generic Python `lib/` rule, so **all 20 files of `web/src/lib/` were untracked** on `feature/js-frontend` (every screen imports `@/lib/...`). A fresh clone could not build the UI. Fixed with `!web/src/lib/` and the files are now committed (they include this build's Track 1 additions to `permissions.ts` and `decimalMath.ts`). Nothing else was hidden by that rule (checked `git status --ignored`).
- The existing `npm run format:check` in `web/` already reported 3 unformatted files before my work (`bridge.ts`, `client.ts`, `mockApi.ts`); I left them alone.

### Commit: checks screen, auto-run after saves, role-based Today (Track 1 finished)
- Added: checks runners over existing data (litres billed vs meters less testing, declared vs expected tenders, tank dip vs book with the T-02 tolerance, credit limit), `GET/POST /api/checks*`, `GET/PUT /api/pump-settings`, a post-write hook that re-runs the affected days after any successful save (today, days with an open shift, days whose shift changed in the last 3 minutes; errors are logged and never break the save), the Checks screen (failures first, area filter, day picker, history, explanation dialog with who/when, every row links to its source records), "Today" with a short list per role (owner: checks, day status, credit outstanding; cashier: shift entry in bundle order; manager: shift close; accountant: checks + credit; attendant: My Shift), sidebar hides masters from the cashier, and `hideFor` in the nav.
- The credit "balance = bills - payments" check I first wrote compared the data with itself, so I **removed** it rather than ship a check that cannot fail. Track 3 adds a real one (balance vs the ageing allocation).
- Tests after Track 1: Python **1561** passed (was 1523; +17 `tests/site`, +6 `test_api_checks`, +route-matrix rows for the new routes); web **330** (was 317); desktop **33** (unchanged); Playwright **48** passed, 8 opt-in skipped (was 46; +2 `checks.spec.ts`: owner sees a failing check and opens its tank, cashier home).
- Judgment calls:
  - Checks run in an API middleware instead of inside the existing services, so no existing service changed.
  - The Playwright test dates its dip check by the **local** day; `setupPump` dates shifts in UTC, which differs from the local day between 00:00 and 05:30 IST (a test-fixture quirk, not a product bug).
  - Owner approvals already record the acting user; three OWNER logins need no code (test added).
- Python run at the end of Track 1 hit no hang.

## Track 2 (started 01:08, elapsed 1h26)
### Commit: docs/daily-report-gap-analysis.md and the spec's status section
- Written first, as asked. Every field of the Classic report mapped to its source or marked MISSING (lubricants, per-mode payment totals, bowser, internal fuel use). Advance/Final, cash book, bank deposits, shortage recoveries, credit sales, tanks, testing, dips already existed and are reused unchanged.
- **NEEDS HUMAN REVIEW (nozzles):** the site notes say 3 dispensers x 4 nozzles; the app has a confirmed rule of exactly two nozzles per dispenser (`MAX_NOZZLES_PER_DISPENSER`, user decision 2026-08-15). Not changed. Workaround: one "dispenser" per physical face (6 dispensers x 2 nozzles). Questionnaire reference: none yet; ask the owner.
- Open questions added here: T-13 (bowser opening stock valuation), T-14 (unapproved expenses on the printed report).

### Commit: Classic daily report, lubricants, bowser, per-mode totals, internal fuel use (Track 2 build)
- Added (new tables, one migration `f73ba7ab62de`, models match migrations - guarded by a test): `LubricantItem`/`LubricantMovement` (append-only, corrections by signed adjustment with a reason), `BowserTransfer`/`BowserBill`/`BowserMeterReading`/`BowserOpening` (voided, never deleted), `ShiftTenderEntry` (a re-typed total voids the old one), `InternalFuelUse` (the litres and vehicle behind an ordinary expense).
- Services/API/screens: lubricants (items, stock, record purchase/sale/adjustment, history), bowser (Stock Transfer through `SaleService` as a credit sale to the internal account `Stock Transfer (Bouser)`, bills, meter, manual opening, A/B/C view, void), "Card / Phone Pay totals" (per-mode totals per shift + internal fuel use), Daily Report page (date picker, Sale Details grid, shift totals vs Total Sale, checks line, Print preview of both sides), `GET /api/daily-report`.
- Report builder: `app/services/daily_report_service.py` computes everything from the database with the owner's formulas; `daily_report_html.py` lays out two A4 sides in the old order with Indian digit grouping. **Verified in real Chromium**: the Playwright test prints the report to PDF and asserts exactly 2 pages, A4 size, and every old section label (`daily-report.spec.ts`).
- Report checks (`report_checks.py`): 15 check kinds, one per formula (tank stock vs the tank's own book, dip vs Total Stock, shift Total = Total Sale, credit list = credit mode, cash book sides, cash in hand not below zero, expenses approved, Oil = sum of Sale x Rate, next opening = previous cash in hand, Total Rs, oil stock not negative, bowser meter = bills, bowser closing >= 0, bowser bill totals). Some compare two independent sources; a few re-add what the report adds and are guards.
- Tests: `tests/api/pump_day.py` builds a synthetic day with the report's structure (tanks MS-22/MS-16/HSD-16/HSD-22, 2 shifts, credit, DTP/PhonePe/Paytm, cash book with 2 deposits, expenses incl. internal fuel, 2 lubricants, bowser) and `test_api_daily_report.py` asserts every formula against hand-worked numbers (13 + 3 check tests); `test_api_site_modules.py` (7); `tests/private/` (figure checker proven on synthetic sheets, 3 + 1 skipped PRIVATE test).
- **PRIVATE regression: `private_samples/` does not exist on this machine** (brief assumed it). The test skips cleanly; `tests/private/README.md` says what to put there. The two known oddities (0.227 gap, 7,453 vs 7,433) are modelled in the checker's tests and listed under `known_oddities`; I could not check them against the real sheet. **Not verified against real figures.**
- Judgment calls (all also in the gap analysis / spec): internal fuel is an expense at the fuel's CURRENT selling price (`Fuel.rate_per_liter`, not the shift date's price) with litres and vehicle and does not touch the tank (T-12 off; with it on the service refuses, since deducting is not built); an expense is printed once entered (pending or approved), a check warns while pending (T-14); the report's Oil figure uses stored line amounts under the default `per_bill` rounding and `money(sum(qty x rate))` under `per_total`; bowser opening Rs is carried at weighted-average cost (T-13); bill number printed is the app's receipt number; an extra shift beyond 2 is built into the data but the printout shows the first two; the bowser internal customer has a huge credit limit and is hidden from bill pickers.
- `reason` boxes on the new void/opening endpoints follow the owner's 2026-10-11 decision (optional in the new UI, recorded as "No reason given").

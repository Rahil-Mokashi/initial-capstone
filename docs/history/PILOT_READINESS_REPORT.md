# Pilot readiness audit

Audit run 15-16 Oct 2026 on branch `feature/lan-multi-user` at `a382280`. Read-only on the repo (this file is the only addition, left uncommitted). All runs happened in scratch copies (`C:\pperp-audit`, `C:\pperp-install`, both deleted at the end). Evidence that is worth keeping (screenshots, walk-through scripts, timing JSON, test logs) is in `C:\Users\Asus\AppData\Local\Temp\claude\c--Users-Asus-Projects-PetrolPumpERP\71e3c2fd-c124-48b9-a7ae-764a035ccaf1\scratchpad\audit-evidence\` (called `EVIDENCE\` below).

Written for: the student developer who is about to put this in front of a real business.

---

## 1. Verdict

**Could the pump run one full real day on this app tomorrow? Only with workarounds, and only on one PC.**
The software itself got through every step of a pump day on a clean synthetic database through the screens (prices, 12 nozzles, tanker receipt, close shift, credit, bowser, bank, payroll, verify / approve / lock, Classic and Plus report). The automated tests are green. What is missing is everything that happens outside this laptop: it has never run on a second machine, a real printer, a real network, or with the owners' real opening balances.

**The 5 biggest blockers**

1. **Nothing has been tried on real hardware.** `docs/LAN_MANUAL_CHECKLIST.md` is 0 of 28 ticked; printing 0/15 (`PRINTING_TEST.md`); offline acceptance 0/10 (`OFFLINE_ACCEPTANCE.md`); firewall and Main PC install scripts only ever ran with `-DryRun`; the installer has only ever been installed on this PC.
2. **The software forbids the pump's real layout.** The app allows 2 nozzles per dispenser (`app/core/constants.py:648`, enforced in `nozzle_service.py:81`); the pump has 3 dispensers x 4 nozzles. I confirmed in the screen: the 3rd nozzle on a dispenser is refused ("maximum 2 per dispenser"). Workaround that works: 6 dispensers of 2 nozzles. Needs the owner's decision (it is an old rule from 2026-08-15).
3. **Day-one opening balances have no home.** There is a screen for tank opening stock, lubricant opening stock and bowser opening stock, but I found no entry for the credit customers' outstanding amounts or for cash in hand (`not found` in the credit router, services and schemas; cash opening is derived from the previous shift). The owners' biggest pain is credit, so this has to be solved before day one.
4. **The app gets slow as data grows, and the cause is in the save path.** After every write the API re-runs all checks before replying (`api/check_hook.py`). On a synthetic year (365 days, 61,084 audit rows, 75 MB) a trivial save (creating a customer) took **6.6 s**, the first one after opening took **190 s** (unexplained, see section 11), and "run checks" alone takes 9.7 s. At 30 days it is about 3 s, on day 3 about 0.5 s. A two-week pilot will feel fine; month three will not. Needs a fix before the pilot grows.
5. **Everything since 9 Oct exists only on this PC.** 58 commits on `feature/lan-multi-user` are on no remote (js-frontend 42, site-visit 51 unpushed). The Git bundles in `C:\Users\Asus\Projects\` are the only other copy. One dead disk loses three weeks of work.

Also serious but not top 5: the default backup interval is 24 h, so a dead Main PC can cost a whole day (section 9); the Close Shift screen leaves the shift "Open" and cannot name an attendant for a shortage (section 5); a price change in the middle of a shift is priced at the rate in force when Close is pressed (code reading, section 5); an owner can approve and lock a day that has a failed check; eight WhatsApp photos in `docs/reference/` are tracked in git and already on GitHub (I did not open them; if they are the owners' real report, that is real data in a repo).

---

## 2. What has and hasn't happened

| Question | Answer | Evidence |
|---|---|---|
| Did the fix batch run? | **Yes** | `FIX_BATCH_REPORT.md`; commits `2e297ec` (path length), `3f6e005` (fuses), `fad4f60` (input scale), `58d9d75` (variance bar), `945bc50` (print harness), `3fc5c36` (lock), `33b8981` (opt-in tests), `e0485fa` (report). |
| Did the Strix security scan run? | **No evidence it did.** `SECURITY_REPORT.md` does not exist; the word "strix" appears in no file in the working tree, and no commit mentions it. Findings count: n/a. | `Get-ChildItem -Recurse` text search, `git log --all --grep=strix` (empty). |
| Was `docs/LAN_MANUAL_CHECKLIST.md` run on real PCs? | **No.** 0 of 28 boxes ticked, no dates, no names. `LAN_REPORT.md` says so itself. | `docs/LAN_MANUAL_CHECKLIST.md`. |
| Installed on a machine other than this one? | **Unknown, no evidence of it.** Only one install is recorded (`%LOCALAPPDATA%\PPERP`, built 15 Oct 08:42). Nothing in any log mentions another PC. | `RESET_POINT.md`, all logs. |
| Real printer, or the owner email, tested for real? | **No / No.** `PRINTING_TEST.md` header: "UNVERIFIED on real hardware", 0/15; only "Microsoft Print to PDF" and OneNote exist on this PC. Email: `mail_service.py` is tested against a fake; "a real mail server" is in `LAN_REPORT.md` NEEDS HUMAN REVIEW. | `PRINTING_TEST.md`, `LAN_REPORT.md:35`. |
| Other things never done | The offline acceptance run; the Qt app and the new app sharing one live database; BitLocker; the scheduled task; real bank file layouts; the private regression test against the owner's real figures (`private_samples/` is not on this machine, the one skipped test in `tests/private`). | logs; `pytest tests/private -rs`. |

---

## 3. Git, branches and builds

**Current branch:** `feature/lan-multi-user` (`a382280`), working tree was clean at the start.

| Branch | Holds | On origin? | Commits not on any remote |
|---|---|---|---|
| `main` | the initial commit only (`50ed634`) | no | 0 |
| `feature/core-framework` | the GitHub default (`origin/HEAD`), `ea25a76` | yes, up to date | 0 |
| `feature/login-screen-enhancements` | core + 4 commits (manual, release fixes), `652c589` | yes | 0 |
| `feature/js-frontend` | login + the whole React/Electron/API work, `6c49542` | **no** | **42** |
| `feature/site-visit-build` | js-frontend + checks, daily report, credit, bank, payroll, shift close, `d17a399` | **no** | **51** |
| `feature/lan-multi-user` | site-visit + LAN, live data, review chain, digest, mail, health, `a382280` | **no** | **58** |

- **Merge state:** a straight line. `core` is an ancestor of `login`, which is an ancestor of `js-frontend`, of `site-visit-build`, of `lan-multi-user` (`git merge-base --is-ancestor` gave 0 for each step). `git merge-tree --write-tree core lan-multi-user` returned a clean tree. So merging into `core` is a **fast-forward, no conflicts expected**: 542 files, +121,262 / -5.
- **Tags:** `pre-ui-changes`, `v1.0.0`, `v1.0.1`, `v1.0.2`, `reset/pre-js-frontend-2026-10-09`, `reset/pre-12h-2026-10-12`, `reset/pre-lan-2026-10-13`. The reset tags are local only. No stash.
- **Uncommitted:** none. Ignored but present: `CLAUDE.md` (gitignored, although the project says it is checked in), `PROMPT_12H.md`, `SITE_NOTES.md`.
- **Which branch for the pilot:** `feature/lan-multi-user` (it contains everything). First push it (and the reset tags), then fast-forward `feature/core-framework`; push before anything else because of blocker 5.
- **CI:** `.github/workflows/tests.yml` and `release.yml` contain no web, desktop or API steps (0 matches for node/npm/web). CI would build the old Qt exe only.
- **Artifact age against the newest source file** (newest source mtime: `api/server.py` 14 Oct 16:37, `web/src` 14 Oct 16:18, migration 14 Oct 16:14):

| Artifact | Built | Stale? |
|---|---|---|
| `dist/PetrolPumpERP.exe` (Qt, 115 MB) | 15 Oct 08:23 | not stale, but it is the **old Qt app, no new feature in it** |
| `web/dist` | 15 Oct 08:04 | no |
| `desktop/sidecar-dist` (Python service) | 15 Oct 08:41 | no |
| `desktop/release/Petrol Pump ERP Setup 0.1.0.exe` (139.8 MB) | 15 Oct 08:41 | no; fresh install worked, migrations reach head `09473165e0f1` |

  HEAD was committed 08:50, after the builds, but no source file changed after 14 Oct, so the builds match HEAD. (Not byte-verified.)
- **Single build command?** No. `desktop/README.md` lists three manual steps in order: `cd web && npm run build`; `pyinstaller api/pperp_api.spec --distpath desktop/sidecar-dist --workpath desktop/sidecar-build`; `cd desktop && npm run dist`. Forgetting step 2 already shipped an old service once (`LAN_REPORT.md`, "Found and fixed" #1). A 10-line script would remove that trap.

---

## 4. Test health

All runs on a scratch copy of the working tree except the Python groups (they ran in place; they write only ignored files).

| Suite | Passed | Failed | Skipped / opt-in | Time |
|---|---|---|---|---|
| Python `tests/api` + `tests/site` | **976** | 0 | 0 | 58 m 37 s (machine shared with other runs) |
| Python everything else (Qt UI, services, backup...) | **999** | 0 | 1 | 15 m 47 s |
| Python total | **1,975** | 0 | 1 | about 74 min |
| Web `tsc`, `eslint`, offline check | clean | | | |
| Web Vitest | **388** (50 files) | 0 | 0 | 78 s |
| Desktop `tsc`, `eslint` | clean | | | |
| Desktop Vitest | **46** (4 files) | 0 | 0 | 22 s |
| Playwright, dev build (real Electron + real Python) | **58** | 0 | **10 opt-in** | 12.3 min |
| Packaged installer tests (against my scratch install) | **4** | 0 | 0 | 36 s |

Numbers match `LAN_REPORT.md` (976 / 999+1 / 388 / 46 / 58+10 / 4). No flaky test and no Python hang this time. (I ran the two Python groups at the same time as other work; no failure resulted, but timings are inflated.)

**Skipped (all by design):**
- Python: `tests/private/test_figure_checker.py:69`, needs `private_samples/` which is never committed. This is the **only** test that compares the report to the owner's real figures, and it has never run on this machine.
- Playwright opt-ins: `deep-path.spec.ts` (needs `PPERP_DEEP_EXE`); 4 in `packaged.spec.ts` (need `PPERP_PACKAGED_EXE`; I ran these separately, 4 passed); `printing.spec.ts` silent print (touches a real printer, so left off); 3 screenshot specs (`SCREENSHOTS=1`).
- Not run: `test:deep-path`, `print-test` (no printer), screenshot specs.

**Format / lint (not part of green):** `prettier --check` fails on 26 web and 24 desktop files; `ruff check` reports 1,941 findings (1,543 auto-fixable) and `ruff format --check` would reformat 283 of 482 files. All pre-existing; not touched.

---

## 5. A full day at the pump, done in the new app

**How I did it:** fresh synthetic database (the app's own template: users `owner1`, `manager1`, `accountant1`, `dataentry1`, `admin1`), real Electron app plus real Python API, driven with Playwright through the screens. **Single PC mode** (Main PC + Client was not walked by hand; `lan.spec.ts` covers one Main PC and one Client on this machine and passed, 4 tests). Master data (nozzles, tanks, a customer, a bank account) was created through the screens in the early parts and through the API for speed in the later parts; each step below says which. Times are wall-clock seconds of automated actions (a human is slower). Screenshots: `EVIDENCE\shots\` (files named `w3-`, `w4-`, `w5-`, `w6-`, `w7-`, `w9-`). Scripts: `EVIDENCE\walk-specs\`.

| # | Step | In the web UI? | Screen | Effort | Result | Notes |
|---|---|---|---|---|---|---|
| 1 | Owner signs in, sets fuel prices | yes | Fuel Prices | 3 prices x (click, 1-2 fields, Save) = 3.7 s | **works** | Petrol, Diesel, Power, prices ship at 0 and the app refuses sales until set. `w3-` `1-fuel-price-dialog` |
| 2a | 3 dispensers x 4 nozzles | **partly** | Nozzles & Dispensers | 12 nozzles = 4 fields each | **blocked as specified, works with workaround** | 3rd nozzle refused: "Dispenser D1 already has 2 nozzles (maximum 2 per dispenser)". With 6 dispensers x 2 all 12 saved (15 s). Fuel type then tank are asked per nozzle; the fresh database has only 2 tanks (T1 Petrol, T2 Diesel), the pump has 4 (Add tank exists: code, fuel, capacity, opening stock). |
| 2b | Open the morning shift | yes | Shifts | 1 dialog (date, shift) 2.3 s | **works** | |
| 2c | Attendants assigned to nozzles | yes | Shifts > shift detail > "Assign nozzle" | per nozzle: employee, nozzle, opening meter | **works with friction** | The app allows **one active nozzle per employee per shift** (409 "already has an active nozzle assignment"). With 4 attendants on 12 nozzles you cannot assign them. This is why Close Shift uses one stand-in record per nozzle (`NOZZLE-N1` ...), which then show up in the Employees list. |
| 2d | Tank dips (4 tanks) | yes | Tanks > Record reading | taken by, physical stock, optional dip value, remarks | **works** | A dip does not change book stock; it is a separate reconcile. |
| 3a | Credit bill | yes | Terminal (and Sales) | pick nozzle, amount or litres, payment = Credit, customer | **works** (screen inspected, form not submitted in my walk; covered by `terminal.spec.ts` + `sales.spec.ts`, passed) | |
| 3b | Bowser stock transfer + bowser bills | yes | Bowser Van | Stock Transfer / Add bill (bill no, customer, litres, rate, transport, vehicle, slip) | **dialog inspected, not submitted** here; API test `test_api_site_modules.py` covers it | Bowser meter and opening stock buttons exist. |
| 3c | Lubricant sales | **partly** | Oil / Lubricants | "Add oil item" only (name, pack, rate) | **friction / unclear** | I found no "record a sale" on this screen; sales movements go through the API (`/api/lubricants/{id}/movements`) and the report. Where the cashier types an oil sale is **not obvious**. Worth asking the developer / checking Terminal. Not checked further. |
| 3d | Internal fuel use (genset, vehicle) | yes | Card, DTP, Phone Pay and PTM totals page (lower half: "Own vehicle / genset fuel") | taken by, fuel, litres, vehicle | **works** (form inspected) | Odd place for it. |
| 3e | Expenses | yes | Expenses > Record expense | 7 fields (category, amount, method, employee, shift ...) | **works** (form inspected) | |
| 3f | Cash collection "Advance" | yes | Close Shift (typed once with Final), or Reconciliation > Record cash movements | 2 fields | **works** | Advance and Final are written once; changing them later is refused ("already recorded"). |
| 4 | Close the shift from a bundle | yes | **Close Shift** | 12 closing readings + testing (pre-filled 5) + 6 money fields: **30 fields, 4.5 s automated** | **works** | Saves all or nothing. Opening reading = previous closing (typed only the first time; I typed 1000). Tally shows Balanced / Short / Excess. First attempt was **refused correctly**: "Cannot issue 469.000; only 196.000 is currently in stock" (tank opening stock was too low). |
| 4b | Cash shortage against an attendant's name | **only elsewhere** | Reconciliation > Record shortage | employee, amount | **partly** | The Close Shift screen cannot name a person (nobody is assigned per nozzle). The shortage can be recorded separately against any employee, but nothing ties it to the tally. Open item in `LAN_REPORT.md`. |
| 4c | Does closing the shift close it? | | | | **friction** | After "Shift closed and saved." the screen still says "Morning (open)" and the Shifts page still shows Open. The shift only becomes Closed with a second action on Shifts. Because `days_to_check` (`api/services.py:652`) re-runs checks for every open shift, forgetting this makes every later save slower. |
| 5 | Evening shift, mid-day price change | **partly** | Fuel Prices, Close Shift | | **works / price change unsupported** | A second shift works the same way. A new price is a new "rate"; a sale keeps the rate at the time it is made, but Close Shift creates one sale per nozzle at close time (`sale_service.py:221` reads the fuel's current rate; `shift_close_service.py` has no rate logic). By code reading, a mid-shift price change reprices the **whole** shift's litres at the new rate. I did not test it. |
| 6 | Bowser fill, 4 bowser bills with transport, meter | yes | Bowser Van | see 3b | **works** (dialogs inspected) | |
| 7 | Tanker receipt for one tank | yes | Tanks > Receipt (quantity, reference, remarks) and Procurement (orders / deliveries) | 2 receipts of 7,000 L = 3.8 s | **works** | T1 went 2,500.5 -> 9,500.5 L. A receipt above capacity is refused. Not tied to a supplier invoice unless done through Procurement. |
| 8 | Accountant verifies; one correction with a reason | yes | Review (Verify); Card/Phone Pay totals page (retype) | 1 click | **works** | Verify: Entered -> Verified in 2.8 s. A retyped figure sends the shift back to Entered (stated on the screen; I did not walk the retype). **Nobody is stopped from verifying their own entry** (default V-06). |
| 9 | Owner reviews digest and checks, approves, locks | yes | Daily digest, Checks, Review | Approve + Lock = 2 clicks | **works with friction** | Approve and Lock happened with **one check failing** ("payment modes ... add up to Total Sale", my own typed ₹60 excess). The app lets an owner lock a day with a failed check. The Locked state then shows "Closed for good" and offers "Reopen..." with a reason. |
| 10 | Daily report Classic and Plus; print; compare to the owner's report | yes | Daily Report | Day + Style select, "Print preview (both sides)", "Finalise this day" | **works, not verified against real report** | Classic headings: Sale Details, Shift 1/2 Transaction Details, Shift 1/2 Cash Book, Shift 1/2 Credit Sale, (back) Expenses Details, Oil Sale, Bowser Van. This matches sections 1-8 of `docs/daily-report-spec.md` one to one. Plus adds "Dip difference" and "Credit". Preview took 3.7 s and opens a separate print window which my screenshot did not capture; PDF/two-page A4 check was done by the 12-hour build in Chromium (`TWELVE_HOUR_REPORT.md`), not repeated by me. The private regression (`tests/private`) **skipped**: no `private_samples/`. So "does it match the owner's real sheet" = **not checked**. |
| 11 | Bank: import a statement for both accounts, match deposits | yes | Bank Matching | upload CSV, then **map columns (header line, date, details, money in, money out, balance, reference, date format)**, Preview, Import, "Check the books against the bank" | **works with friction** | I got as far as choosing the file and seeing the mapping form (`w6-bank-chosen.png`); the full import and match flow is covered by `bank.spec.ts` (passed) and 30+ API tests. Every new bank needs a one-off column layout ("Save layout" exists). PDF statements are not supported. |
| 12 | Credit: statement, ageing, recovery note | yes | Credit, Credit Ageing, customer page | click customer; "Log follow-up" (how, what was said, promised date, amount) | **works** | Customer page shows limit, owes now, 0-30 / 31-60 / 61-90 / 90+, overdue-by days, bills; Export PDF / Excel / Print preview. Ageing page lists "To chase today". 2.3-2.9 s per page. |
| 13 | Payroll: register for two staff, approval, payslip | yes | Payroll | set salary (1 field), Prepare, owner "Approve this month", "Mark paid" dialog (cash / bank, date, reference), "Payslip" | **works with friction** | Two traps: (a) "Set salary" applies **from the first of the current month**, so "prepare last month" produced an **empty register** (first attempt); preparing the current month worked (14 of 31 days, ₹18,000 -> ₹8,129.03); (b) an employee with no salary is silently left out of the register. I reached the "Mark paid" dialog and the Payslip button but did not click through to a PDF. Only one of two staff was paid (the second had no salary set on purpose). No payroll Playwright test exists; one web test + API tests only. |

**Summary of what blocks a real day today:** nothing is "Qt only" any more, but the day needs (a) the nozzle-cap workaround, (b) a way to enter opening credit balances and cash, (c) a decision about shortages per person, (d) the shift not being closed by the close screen, (e) clarity about where oil sales are typed.

---

## 6. Feature inventory against what the owners asked for

Status: built / partial / missing. "Tests" = counted from files; "Web UI" = a route in `web/src/components/nav.ts` and a screen I opened.

| Area | Status | Web UI screen | Tests | Evidence |
|---|---|---|---|---|
| Roles, three owner logins | built | Users | `test_api_users`, route matrix | `DATA_ENTRY`, `ACCOUNTANT`, `OWNER` roles; per-owner reviewed marks (`TWELVE_HOUR_LOG.md`, `LAN_LOG.md`) |
| Data-entry home | built | Today (short list per role) | `test_api_checks` + web | Data entry menu: Tanks, Terminal, Sales, Shifts, Credit, Close Shift, Expenses, Oil, Bowser, Reconciliation, Daily Report (`w`/`dataentry1` survey) |
| Checks engine + Checks screen | built | Checks | `test_api_checks`, `checks.spec.ts` | 11-18 checks per day; failures first; "Add an explanation" cannot change the result |
| Owner daily digest | built | Daily digest | `test_api_staff_digest` | Shows totals, failed checks, waiting items, "Mark as reviewed" |
| Staff performance | partial | (facts report in digest/API) | `test_api_staff_digest` | "facts, not a score" by design; nobody is named per nozzle in the new flow, so little to report |
| Daily report Classic | built | Daily Report | `test_api_daily_report` | structure matches spec; real-figure test skipped |
| Daily report Plus + finalise | built | Daily Report | same | "Finalised, code a3c7b943..."; figures-changed warning |
| Lubricants | partial | Oil / Lubricants (item list only) | `test_api_site_modules` | no sale entry found in the screen |
| Bowser | built | Bowser Van | same | stock transfer, bills, meter, opening |
| Cash collections (Advance / Final) | built | Close Shift, Reconciliation | `test_api_close_desk` | write-once |
| Internal fuel use | built | Card/Phone Pay totals page | same | recorded as expense at selling price, no tank deduction (T-12) |
| Credit: history, ageing, limits, recovery log, statements | built | Credit, Credit Ageing | `test_api_credit_control`, `credit.spec.ts`, `credit-control.spec.ts` | over-limit default is "warn" (V-14) |
| Bank import and matching | built, not tested on a real bank file | Bank Matching | `test_api_bank_recon`, `bank.spec.ts` | CSV/XLSX only; layout mapped by hand once per bank |
| Accounts login, payroll, payslips | built | Payroll | `test_api_payroll`; 1 web test; no e2e | Excel salary import deferred (U-02); shortage recovery not posted back |
| Entered / Verified / Approved / Locked | built | Review | `test_api_entries` | locked shift refuses every write path (`entry_lock_guard.py`) |
| Self-verification blocked? | **no, by default** | | | V-06 default: "nobody is stopped from verifying their own entry" |
| Testing quantity default | built | Close Shift (5 L pre-filled), Owner Choices | `test_api_close_desk` | T-15, default 5 |
| LAN modes, enrolment, mutual TLS, firewall script, devices | built, **never on real PCs** | Devices, Network setup | `tests/api/lan` (attacker, guardrails, keys, live, main pc, scripts), `lan.spec.ts` | scripts only dry-run |
| Live updates and conflict handling | built | everywhere | `test_lan_live.py` | "Changed by Asha at 14:05"; no special reload button on each form |
| Outbox owner email | built, **never sent for real** | Email summary | `test_api_mail` (10) | off by default; DPAPI password file |
| Backups, integrity, health, restore-and-promote | built; restore tested only on synthetic backups | Backups, System health | `test_backup_restore`, `test_api_system_health` (15) | see section 9 |
| Shift-close entry screen | built | Close Shift | `test_api_close_desk`, `close-shift.spec.ts`, `shift-close.spec.ts` | no per-attendant names, does not set shift to Closed |
| Price change mid-shift | **missing** (see step 5) | Fuel Prices | none | by code reading |
| Tanker receipts | built | Tanks, Procurement | `test_api_tanks`, `procurement.spec.ts` | |
| Attendance and leave | built | Attendance, Leave | `test_api_attendance`, `attendance.spec.ts` | payroll uses it |
| First-run setup for a new pump | **missing** | none | none | only a Qt-era runbook (`docs/first-shift-runbook.md`) |
| Old Qt screens still needed | none found | | | section 7 |

---

## 7. Qt app vs new web app

The new nav (`web/src/components/nav.ts`) has a screen for **every** Qt module. Mapping of the 42 Qt UI files:

| Qt module | Web | Coverage |
|---|---|---|
| Login, lock screen, set PIN, change password, forgot password | login, account menu | full, except **Windows Hello** (not offered; password or PIN always work) |
| Dashboard / landing groups / alert strip / notifications | Today, dashboard, Alerts | full |
| Employees, Users, Fuel prices, Tanks, Nozzles | same names | full (nozzle cap rule is the same in both) |
| Terminal, Sales (+ receipts), Shifts, My Shift | same | full |
| Attendance, Leave | same | full |
| Credit, Expenses, Reconciliation | same | full (web adds ageing, limits, recovery, statements) |
| Procurement | Suppliers, Purchase Orders, Invoices | full |
| Reports hub, table reports, print/PDF/Excel | Reports | full |
| Analytics | Business insights | full |
| Backups, Audit log, Settings | Backups, Audit Log, Company Profile, Owner Choices | full |
| Support | Support | full |
| Terminal settings (recent usernames, login language) | not found | **not checked** whether the login-language switch exists |

Everything that is new (checks, Close Shift, daily report Classic/Plus, bowser, lubricants, bank matching, payroll, digest, review chain, devices, mail, health) exists **only** in the new stack. The Qt exe (`dist/PetrolPumpERP.exe`) contains none of it (`TWELVE_HOUR_REPORT.md`).

**Can the pilot run on the new app alone? Yes.** Staff do not need the Qt app. Do not run both on the same live database (untested, `FIX_BATCH_REPORT.md`). Installed apps share the Qt app's data folder by default (`%LOCALAPPDATA%\PetrolPumpERP`), so **a pilot install on a PC that ever ran Qt will open the Qt database**. Decide on purpose which database the pilot uses.

---

## 8. Open owner questions and the defaults in force

Highest risk first. "Where" is the place that holds the default.

| Risk | ID | Question | Default in force | Where |
|---|---|---|---|---|
| **HIGH** | nozzles | 3 dispensers x 4 nozzles, or 2 per dispenser? | 2 per dispenser (old rule) | `app/core/constants.py:648` (code, **not** a setting) |
| **HIGH** | V-06 | Who may verify / approve / lock; can someone verify their own entry? | one owner approves and locks; nobody blocked from verifying own entry; a day can be locked with failed checks | `pump_settings_service.py:58` `owner_lock_rule` |
| **HIGH** | T-01 | Are shift litres already net of testing? | testing shown, not added back | `add_testing_back` = off |
| **HIGH** | T-15 | Usual testing per nozzle | 5 L, pre-filled; meter counts it and it is subtracted from litres sold | `default_testing_litres` = 5 |
| **HIGH** | T-06 | Exactly what Advance and Final mean | typed cash collections on the shift cash book | `TWELVE_HOUR_REPORT.md` |
| **HIGH** | H-02 | Which payment mode lands in which bank account; date window | per-account setting; window 4 days | `bank_date_window_days`; account modes screen |
| **HIGH** | (new) | Opening balances: credit customers, cash in hand | no entry found | see section 5/10 |
| **HIGH** | (new) | Shortage against a named attendant | cannot be named on Close Shift | `LAN_REPORT.md` |
| **HIGH** | L-01 | How old may the last backup be? | backup every 24 h; "older than 36 h warns" | `backup_interval_hours`, `backup_max_age_hours` |
| MEDIUM | T-03 / T-04 | Rounding per bill or on totals | each bill to paise, ROUND_HALF_UP, totals add rounded bills | `rounding_rule` = per_bill |
| MEDIUM | T-12 | Does internal fuel also reduce tank stock? | no | `internal_fuel_deducts_tank` = off |
| MEDIUM | T-13 | How bowser opening stock is valued | yesterday's closing litres at weighted-average cost | daily report code |
| MEDIUM | T-14 | Do unapproved expenses belong on the printed report? | yes, a check warns | |
| MEDIUM | T-02 | Dip vs book tolerance | 0.5 % | `dip_tolerance_percent` |
| MEDIUM | V-14 | Credit over the limit | warn, owner can allow with own password | `credit_over_limit` = warn |
| MEDIUM | V-10 | New credit customers need approval? | no | `new_customer_approval` = off |
| MEDIUM | V-03 / V-04 | What the cashier role may do | shift, sale, expense, reconciliation entry; no approvals, users, prices | `DATA_ENTRY` in `app/core/constants.py` |
| MEDIUM | U-08 / U-09 / H-24 | Accountant's access | payroll, expenses, bank matching, credit view/recovery, daily report | |
| MEDIUM | U-04 | Salary rules | prorated by calendar days present; leave and holidays unpaid; deductions typed | `payroll_*` settings |
| MEDIUM | (new) | Mid-shift price change | whole shift priced at the rate at Close | code reading |
| LOW | H-09 | Bank charge tolerance | 2 % | `bank_fee_tolerance_percent` |
| LOW | T-00 | Which report style is default | Classic | `daily_report_style` |
| LOW | J-05 | Which bills carry vehicle/slip numbers | bowser always, credit on request | |
| LOW | V-01 / V-02 | Order of the paper bundle | credit bills, closing readings, mode totals, expenses, oil, bowser, Advance/Final/deposits | Close Shift layout |
| LOW | Q3 / Q7 / V-18 | What DTP Card is; bill number series; product in MS-22 / MS-16 | app receipt number printed | |
| LOW | L-02..L-17 | Backup / mail times and server | see `pump_settings_service.py` | |

Two figures on the owner's old sheet (a 0.227 gap in Shift 1; an expense total off by 20) are listed as oddities and are intentionally not reproduced (`tests/private/README.md`).

**Questions to ask at the pump before the pilot, in order:** nozzle layout; opening credit balances and cash in hand; T-01 / T-15 testing; who verifies and locks (V-06) and whether a failed check should stop a lock; what Advance and Final mean (T-06); which bank account gets which payment mode (H-02); how a price change during a shift is handled; where oil sales are entered; who is billed for a shortage.

---

## 9. Security and data safety

**What protects the app today (tested):** Python and Electron run only on loopback in Single PC mode with a per-launch secret; Electron hardening and fuses (`shell.spec.ts` 8 tests, `packaged.spec.ts` 4); strict CSP and an offline request blocker; build check fails on external URLs (passed); passwords hashed, forced change of the default `admin` / `Admin@123` (`seed.py:176`); RBAC with a route matrix test; append-only, hash-chained audit log with a verify action; a Main PC refuses to start unless every protection is on, mutual TLS with device tokens, 5-wrong-codes pairing lockout (`tests/api/lan/test_lan_attacker.py` 12 tests); a locked shift refuses every write path.

**Only tested in dry run:** `install-main-pc.ps1` and `firewall-main-pc.ps1` (`-DryRun` only), the scheduled task at boot, the "task restarts the service" behaviour.

**Never tested:** anything on a second machine or a real network; BitLocker; the data-folder ACL against a standard Windows user; the firewall rule; a real SMTP server; a real printer; the offline acceptance run; Strix or any external security scan (section 2).

**Dependency audits (run now):**
- `npm audit --omit=dev` in `web/`: **0 vulnerabilities**.
- `npm audit` in `desktop/`: **8 moderate**, all in the build tooling (`electron-builder` and its dependency chain: `app-builder-lib`, `dmg-builder`, `electron-builder-squirrel-windows`), not in what runs at the pump.
- `pip-audit -r requirements.lock`: **52 known vulnerabilities in 6 packages**: pillow (35), pypdf 6.16.1 (8; fixed in 6.17-6.19), anyio 4.14.0 (3; fixed in 4.14.2), python-dotenv (2), pygments 2.19.2 (2; fixed in 2.20.0), idna 3.10 (2; fixed in 3.15). Full list: `EVIDENCE\pipaudit.txt`. The app is offline and only parses files the owner picks (bank CSV/XLSX, PDFs, images), so exposure is mostly "malformed file" rather than "remote attacker", but pillow and pypdf are exactly the libraries that parse such files. Not fixed (read-only audit). Note that `anyio` was deliberately pinned to 4.14.0 to keep another pin (`FIX_BATCH_REPORT.md`).

**NEEDS HUMAN REVIEW items gathered from all logs:**
- Nozzle cap vs 3 x 4 layout; `CreditService.limit_override` (one additive `if`); Shift Close stand-in employees (`NOZZLE-N1` visible in Employees); DATA_ENTRY and ACCOUNTANT permission defaults; shortage recovery through salary not posted into the shortage ledger (`TWELVE_HOUR_REPORT.md`).
- V-06 default, T-15 default, shortage cannot be pinned on a person; conflict messages have no "reload" button; Shift Close missing per-attendant detail; formatting drift; installer has the default Electron icon and is not code-signed (`LAN_REPORT.md`).
- Policy decisions on forced password change server-side, over-precise decimals, fuel lookup permission; `GrantFileProtocolExtraPrivileges` fuse still on; sidecar bundle carries unneeded packages (`lxml`, `mypy`, `psutil`, `setuptools`, `yaml`); a Qt/new-app shared database untested (`FIX_BATCH_REPORT.md`).
- Windows Hello not offered; "restore overwrites the live database file under a running server, exactly as Qt does; restart afterwards" (`JS_MIGRATION_LOG.md:281,290`).

**Is the database protected on disk?** **No encryption in the file.** It is a plain SQLite file; SQLCipher was considered and rejected on purpose (`PROJECT_CONTEXT.md:631`). Protection is meant to come from BitLocker plus a data-folder ACL limited to SYSTEM and Administrators (set by the install script; not run for real). System health shows a red "Disk encryption" line until BitLocker is on. On a PC that is not set up with the script (a normal Single PC install) the file sits in `%LOCALAPPDATA%\PetrolPumpERP`, readable by that Windows user.

**Backups and restore:** the app took a scheduled backup by itself when I started the installed app, and a `pre_migration` backup (697 KB) before applying migrations (section 10). Default interval **24 h** (L-01), nightly integrity and audit-chain check at 02:00, an encrypted copy to a USB/network folder if one is configured (needs a folder and a passphrase set by a person). Restore and `lan promote` are tested with synthetic backups (`test_backup_restore`, `test_api_system_health`); **never restored from a real backup on a second PC.**

**If the Main PC dies mid-shift:** everything committed up to the last backup is recoverable; everything entered since the last backup is lost (up to a day at the default, "re-enter from the paper bundle", `MAIN_PC_RUNBOOK.md` section 4). SQLite WAL means a crash itself does not corrupt committed data. Expect "about an hour for a technician"; the replacement needs a new certificate authority and every Client re-paired. Until an off-device folder and passphrase are set, a dead disk takes the backups with it.

---

## 10. Install, update and first-day setup

Done on this machine, in `C:\pperp-install`, with a scratch copy of the data (the real `%LOCALAPPDATA%\PetrolPumpERP` database and the real install at `%LOCALAPPDATA%\PPERP` were not touched; I backed up and restored the one registry uninstall key the installer rewrites).

| Check | Result |
|---|---|
| Installer size | **139.8 MB** (`Petrol Pump ERP Setup 0.1.0.exe`); installed **441 MB** |
| Fresh silent install (`/S /D=...`) | exit 0 in **33 s** |
| Start-up | **7.2 s** to a titled window (machine busy); the packaged test measured **4.4 s** to the login screen |
| Memory | **499 MB** total working set (4 Electron processes at 48-103 MB, the Python service 156 MB) at idle on the Tanks screen |
| Packaged tests against the install | 4 passed |
| Install again over the existing install (same version 0.1.0) | exit 0; app started |
| Upgrade with data: a database built with the 12 Oct code (27 migrations, rev `b12dbe7bfb5c`, 5 employees, 3 customers) opened by the new service | **migrations applied up to `09473165e0f1`**; a `pre_migration` backup was created first; employees 5, customers 3 kept; `integrity_check` ok; no foreign-key violations; 78 tables; start-up 7.2 s |
| **Not possible to test** | upgrade from an older *installer* (only one installer version exists); install on a second machine; install over a different Windows user's data |

Caveat: all of the above used one installer version on one PC. The installer is unsigned (SmartScreen will warn) and has the default Electron icon.

**First-run setup for a new pump?** **No wizard.** A first launch asks you to sign in as `admin` / `Admin@123` and forces a password change. Everything else is manual, in this order (`docs/first-shift-runbook.md`, Qt-era wording, still accurate except the nozzle-cap and Qt UI references): fuel prices (ship at 0) -> tanks with real opening stock -> dispensers and nozzles -> employees -> users -> credit customers and accounts -> shifts. Company profile is on the Company Profile screen.

**How would the owners' opening balances get in on day one?**

| Balance | Possible today? |
|---|---|
| Tank stock | **yes**, "Opening stock (L)" when adding the tank |
| Lubricant stock | **yes**, a movement of kind "opening" (API; screen not checked) |
| Bowser opening stock | **yes**, "Opening stock" button on Bowser Van (litres and rupees) |
| Credit customers' outstanding | **no direct entry found.** A workaround is to back-date a bill for each customer (what I did in the demo, via a bowser bill), but that fakes bill numbers, fuel and stock movement. Needs a proper "opening balance" entry. |
| Cash in hand | **no.** Opening cash of a shift is derived from the previous shift; the first shift starts at 0 (`shift_cash_book_service`: "opening_balance ... derived, never columns"). |
| Bank balances | the first imported statement carries its own opening balance |
| Staff salaries | yes, per employee in Payroll (applies from the 1st of the current month) |

---

## 11. Performance with realistic data

Synthetic data generated through the API with `EVIDENCE\genyear.py`: 365 days, 2 shifts a day, 12 nozzles (about 17,000 L a day), 10 credit bills a shift, 4 bowser bills a day plus a transfer and a meter, 2 expenses and an oil sale a shift, 4 tank receipts every 4th day, 3 bank lines and 1 cash deposit a day. End state: 730 shifts, **61,084 audit rows, 74.7 MB database**. The check hook was switched off **in my script only** to build the data in about 73 minutes (with it on, 3 days took 5 minutes). Timings below are in-process API calls (no network); a screen adds the browser's own render time. Checkpoints were taken while other jobs were running, except the "write latency" row which ran on an idle machine.

| What | 30 days | 90 days | 180 days | **365 days** |
|---|---|---|---|---|
| Daily report Classic | 0.4 s | 0.7 s | 1.6 s | **2.9 s** |
| Daily report Plus | 0.3 s | 0.9 s | 1.8 s | **3.0 s** |
| Checks run (one day) | 3.2 s | 4.9 s | 7.0 s | **9.7 s** |
| Daily digest | 0.6 s | 0.9 s | 2.0 s | **3.4 s** |
| Bank match run (30 days) | 1.9 s | 2.5 s | 3.9 s | **5.5 s** |
| Audit "verify chain" (all) | 0.1 s | 0.7 s | 1.1 s | **2.3 s** |
| Dashboard summary | 0.05 s | 0.4 s | | **0.9 s** |
| Credit ageing / customer list | 0.1 / 0.2 s | 0.2 / 0.2 s | | **0.6 / 0.6 s** |
| Bank "days" table, tanks, shifts, sales page, reports hub, audit page | all under 0.3 s | | | all under 0.3 s |
| Writing: one data-generation day (about 100 writes, hook off) | 4.9 s | 7.1 s | 9.9 s | 14 s |

**Over 2 seconds at a year:** daily report (both styles), checks run, digest, bank match, audit verify. Daily report Classic crosses 2 s between day 180 and 365; the checks already cross it by day 30 (partly because other jobs were running; the true value on an idle machine is lower, but the growth is real).

**The one that matters most:** with the check hook ON, on the year database, on an idle machine, a plain save (create a customer, 3 tries): **190 s (first), then 6.6 s, 6.9 s**. Cause: `api/check_hook.py` runs every check for "today plus every open or just-changed shift" after every write, synchronously, before the response returns (`days_to_check` at `api/services.py:652`), and the checks scan history that grows daily. The 190 s first call I could not explain (a possible cold-cache effect, or a backlog of checks on first use); it should be reproduced on a real installed app. For the pilot (two to four weeks of data) saves should stay around 0.5-3 s; for a full year it is not usable.

**Start-up and screens:** app start 4.4-7.2 s on a 3-day database; startup on the 365-day database was **not measured in the packaged app** (the app on the year database was not launched; not checked). Screen load times measured in the walk-through on small data: 1.0-3.6 s per screen in the automated browser (includes a fixed 0.9 s wait).

---

## 12. Code and docs health

- **Stale docs:** `PROJECT_CONTEXT.md` is 339 KB (1,170+ lines) in diary order. Sections that no longer match the code: "Current Module" (says Phase 9 Tank & Inventory), "Pending Modules" (lists payments, credit and reconciliation as not built; they are built), "Known Limitations", "Deployment Status" (Inno Setup + Qt only; the Electron NSIS installer is not described there), "Next Task" (line 1118, predates the site-visit and LAN work). `ROADMAP.md` (last changed 13 Oct) has **0** mentions of "Main PC", "Electron", "React" or "digest"; its Phase 3 still carries a "marked done originally but never wired" note. `web/src/components/nav.ts` header comment says the rest "are listed ... but marked soon"; every item has a route now. The user guide, administrator guide and recovery guide (`docs/`) are Qt-era; `docs/first-shift-runbook.md` says "Each dispenser takes exactly two nozzles". `LAN_SETUP.md` exists at the repo root, not under `docs/` where the brief and other docs refer to it.
- **Size:** `app/ui` (Qt) 13,266 lines + 858 QML; `app` non-UI 17,561; `api` 6,396; `web/src` 41,836; `desktop/src` 1,766; `tests` 20,824. Largest hand-written files: `app/ui/main_window.py` 1,942, `app/ui/procurement_window.py` 1,005, `scripts/build_manual_pdf.py` 821.
- **Dead Qt code:** all 42 Qt UI files plus 26 `*_ui.py` test files and 2 window tests are now replaced by screens in the web app. They are still the shipping exe, still built by CI, and add about 20 minutes to the Python test run. Do not delete before the pilot; decide after.
- **Duplicated:** `describe_unexpected_error` exists twice (`api/errors.py` and the Qt original); the sidecar carries unneeded packages.
- **Tracked files that should not be there:** 8 WhatsApp images in `docs/reference/` (on GitHub); a 2.9 MB manual PDF; `web/src/api/openapi.json` (768 KB) and `schema.d.ts` (469 KB) are generated.
- **Unformatted:** see section 4 (26 + 24 prettier, 283 ruff-format, 1,941 ruff findings).
- **TODO / FIXME:** 0 real ones in `.py/.ts/.tsx` (the 10 grep hits are `XXXX` bank-mask text).
- **Housekeeping / disk cleanup (done at the end, about 2.3 GB freed on C:):** deleted only regenerable things: my two scratch folders (`C:\pperp-audit` 1.1 GB, `C:\pperp-install` 470 MB), `desktop/release/win-unpacked` (441 MB, rebuilt by `npm run dist`), `build/` (150 MB, PyInstaller work folder), `desktop/sidecar-build` (54 MB), `desktop/test-results` (47 MB), `.pytest_cache`, and 18 `__pycache__` folders. Nothing tracked by git was touched (`git status` shows only this report). **Kept on purpose:** `dist/PetrolPumpERP.exe`, the installer in `desktop/release`, `desktop/sidecar-dist`, both `node_modules` (760 MB, needed to run tests), `web/dist`, `graphify-out` (64 MB), `app/backups` (19 MB, 18 dev-database backups: they are backups of the developer's database, so I left the decision to you), the three `.bundle` files and `PetrolPumpERP-reset-2026-10-09` next to the repo (your rollback copies). Candidates for you to decide: old bundles after pushing (blocker 5), and the `docs/reference` photos.
- **What will slow the next two weeks:** the full Python suite takes about 74 minutes and the three build steps are manual; CI does not test the new stack; the Qt tests still run on every change; the save-path check hook makes bulk testing slow.

---

## 13. Pilot backlog for the next 12 hours

Effort: S under 1 h, M 1 to 3 h, L over 3 h. "Owner answer" lists the ID that must be settled first.

### Must-have for day one

| # | What and why | Effort | Depends on | Owner answer |
|---|---|---|---|---|
| 1 | Push `feature/lan-multi-user` and the reset tags to origin; fast-forward `feature/core-framework`. Removes the single-copy risk. | S | none | no |
| 2 | Decide nozzle layout: make the cap a setting (default 4) or keep 6 dispensers of 2. A setting is a one-file change plus a migration-free default. | M | owner answer | **nozzles** |
| 3 | Opening balances: an "opening balance" entry for each credit customer (an adjustment with a reason, dated before day one) and for cash in hand. | M-L | design of the entry | opening figures |
| 4 | Make "Close shift" on the Close Shift screen also close the shift (or show a clear second step), so open shifts do not pile up and slow every save. | S | none | maybe V-01/V-02 |
| 5 | Reproduce the first-save delay (190 s) on an installed app on the year database; if real, fix. Make the check hook asynchronous or limited to the changed day, so a save returns in under a second. | L | #4 | no |
| 6 | Single Main PC dry run **on the real hardware**: install, firewall, BitLocker, second PC pairing, `docs/LAN_MANUAL_CHECKLIST.md` top to bottom with names and dates. | L (at the pump) | PCs, router | no |
| 7 | Real printer test (`PRINTING_TEST.md`): Classic report on A4 both sides, receipt printer if used. | M (at the pump) | printer | no |
| 8 | Backup: set an off-device folder and the passphrase in System health; lower "Take a backup every" to 1-2 hours for the pilot. | S | USB / folder | L-01 |
| 9 | Run `OFFLINE_ACCEPTANCE.md` once with the network unplugged. | S | install | no |
| 10 | Make the owners' choices at the pump (section 8, HIGH rows) and set the settings on **Owner Choices**. | M | owners present | V-06, T-01, T-06, T-15, H-02 |
| 11 | Ask the owners if the 8 `docs/reference/*.jpeg` WhatsApp images are their real report; if so, remove them from the repo and its history (they are on GitHub). | S-M | answer | no |
| 12 | Decide which database the pilot uses (new, not the Qt `%LOCALAPPDATA%\PetrolPumpERP` one) and write it in the runbook. | S | none | no |

### Should-have in the first week

| # | What and why | Effort | Depends on | Owner answer |
|---|---|---|---|---|
| 13 | Shift-close shortage against a named attendant (or a clear rule for who is billed). | M | owner answer | who bears a shortage |
| 14 | Mid-shift price change: price a nozzle's litres at the rate by time, or split the close at the change. | L | owner answer | price-change handling |
| 15 | Block (or warn loudly on) locking a day with a failed check; block self-verification if the owners want it. | S | V-06 | V-06 |
| 16 | Where does the cashier type an oil sale? Make it a visible button on Oil / Lubricants. | S-M | none | no |
| 17 | Update `pypdf` (>= 6.19), `anyio` (>= 4.14.2), `pygments`, `idna`, Pillow in `requirements.lock`; rebuild; re-run tests. | M | none | no |
| 18 | One build script for web, sidecar, installer, in the right order, failing if any step is skipped. | S | none | no |
| 19 | Payroll: let "Set salary" take an effective date (so the first run can cover last month) and list staff with no salary on the register. | S-M | none | U-04 |
| 20 | First-run wizard or a one-page checklist screen: tanks, nozzles, staff, users, credit, opening balances. | L | #2, #3 | no |
| 21 | Add a Playwright test for payroll and for the Close Shift -> Review -> Lock chain in one run. | M | none | no |
| 22 | Code-sign the installer and give it an icon. | M | certificate | no |

### Can wait

Qt app retirement and deleting `app/ui`; running the formatters (prettier, ruff); rewriting stale parts of `PROJECT_CONTEXT.md` and `ROADMAP.md`; Windows Hello; PDF bank statements; Excel salary import (U-02); a "reload" button on conflict messages; excluding unused packages from the sidecar; CI for the new stack.

### What the developer must do in person at the pump, in this order

1. Ask the owners the section 8 questions (nozzle layout, opening credit and cash, V-06, T-01 / T-15 / T-06, H-02, price change, shortage, oil sale, bank account list).
2. Collect the opening figures: each credit customer's outstanding, tank dips, lubricant stock, bowser stock, cash in hand, bank balances, staff salaries.
3. Pick the Main PC; BitLocker on; fixed address; install and run the Main PC scripts for real (after the dry run).
4. Install the Client PC(s); pair; run `docs/LAN_MANUAL_CHECKLIST.md` with the owners watching.
5. Plug in the real printer; run `PRINTING_TEST.md`; print a Classic report next to the owners' paper one.
6. Set the backup folder and passphrase; take and restore one backup on a second PC.
7. Run the offline acceptance with the network unplugged.
8. Enter the opening data, then do one shift **in parallel with the old Java tool and the paper bundle** before trusting the new one alone.

---

## 14. Appendix

**Environment:** Windows 11 Home Single Language 10.0.26300; Python 3.13.5; Node v22.18.0; git 2.49.0.windows.1; Electron, Vitest 5.0.3 and Playwright from `desktop/package-lock.json` (Electron version not read separately: not checked).

**Main commands:**
- `python -m pytest tests/api tests/site -q -p no:cacheprovider` (976 passed, 58 m 37 s) and `python -m pytest tests --ignore=tests/api --ignore=tests/site -q -p no:cacheprovider` (999 passed, 1 skipped, 15 m 47 s)
- `cd web; npm run typecheck; npm run lint; npm test; npm run check:offline`; `cd desktop; npm run typecheck; npm run lint; npm test`
- `cd desktop; npx playwright test` on the copy (58 passed, 10 skipped, 12.3 min) and `PPERP_PACKAGED_EXE=<scratch install> npx playwright test e2e/packaged.spec.ts` (4 passed)
- `npm audit --omit=dev` (web), `npm audit` (desktop), `python -m pip_audit -r requirements.lock`
- Install: `"Petrol Pump ERP Setup 0.1.0.exe" /S /D=C:\pperp-install\fresh`; upgrade DB built from `git archive --format=zip reset/pre-12h-2026-10-12 app alembic alembic.ini`
- Data: `python -I genyear.py 365 30,90,180,365` with `PETROL_PUMP_DB_PATH` on a scratch file
- Git: `git merge-base --is-ancestor`, `git merge-tree --write-tree`, `git rev-list --count <branch> --not --remotes`

**Where things are:** `EVIDENCE\` (see top) holds `shots\` (about 90 screenshots and the `walk*.json` step logs), `walk-specs\` (the Playwright scripts), `genyear.py`, `year.json` and `year.log`, `pw_dev.txt`, `py_*.txt`, `pipaudit.txt`. The scratch copies (`C:\pperp-audit`, `C:\pperp-install`) were deleted at the end.

**Not checked (and why):** Main PC + Client walk by hand (only `lan.spec.ts`); packaged app on the year database; real printer; real bank layouts; real owner figures (no `private_samples/`); the 8 WhatsApp images (not opened on purpose); Electron version number; whether the Qt login-language setting exists in the web login; oil-sale entry on the screen; Classic/Plus PDF page count (relied on the 12-hour build's check); the 190 s first-save delay (not reproduced or explained).

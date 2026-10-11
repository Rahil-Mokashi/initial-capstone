# JS front-end migration - proof phase report

Branch `feature/js-frontend` (never pushed). Reset point: tag `reset/pre-js-frontend-2026-10-09`, see `RESET_POINT.md`.
Details and every judgment call: `JS_MIGRATION_LOG.md`. Decision record: `docs/adr-js-frontend.md`.

## What was built
- `api/`: FastAPI sidecar over the unchanged services (auth, tanks, two lookups, health, graceful shutdown).
- `desktop/`: Electron shell (sidecar lifecycle, single instance, hardening, offline blocker, print bridge, error screen), Playwright tests, packaging.
- `web/`: React + TypeScript UI: shell, login, forced password change, data table, form primitives, dialog, toast, error boundary, and the Tanks screen.
- Untouched, verified by diff against the reset tag: `app/`, `alembic/`, existing `tests/`, both `.spec` files, the Inno Setup installer, CI.

## Final test counts (run on the final code)
| Suite | Result |
|---|---|
| Python (996 baseline + 107 new `tests/api`) | **1103 passed**, 0 failed (8m49s, no hang) |
| Web unit (Vitest) | **104 passed** |
| Desktop unit (Vitest) | **29 passed** |
| Playwright, real Electron + real Python API | **28 passed**, 3 skipped on purpose (screenshots, installed-app smoke, silent print: they need opt-in env vars) |
| Installed-app smoke (`PPERP_PACKAGED_EXE`) | passed when run (start, login, Tanks, receipt, graceful quit) |
| Build offline gate | passed |

## Git log of the branch
```
1808674 build: package the API as a PyInstaller sidecar and the app as an NSIS installer, with packaged smoke test and measurements
928af13 feat: add printing spike (A4 report and 80 mm receipt to PDF from the real Qt HTML builders)
5537246 feat: add Electron shell with sidecar lifecycle, offline guards, printing bridge and end-to-end tests
340b782 feat: add Tanks proof screen (list, detail, readings, transactions, reconcile, status) to the web UI
3ec6136 feat: add web front-end foundation (shell, login, shared components, API client, design tokens)
8d556d9 docs: tidy migration log
e5e96dc feat: add local FastAPI layer with auth and tanks endpoints plus tests
a8ab100 build: add fastapi and uvicorn for the local HTTP API sidecar
cb3879b docs: add ADR and migration log for the JS front-end migration
b945d1d docs: record reset point and rollback steps before the JS front-end migration
```
(plus the final docs commit that adds this report)

## Tanks parity checklist (Qt `tank_window.py` vs new UI)
| Qt feature | New UI |
|---|---|
| Gauge cards: code, fuel, status, % fill, stock / capacity, low-stock cue | Done (percent printed, "Low - 18.0%" badge with icon) |
| Table: code, fuel, capacity, stock, status, open | Done (Table view toggle) |
| Recent transactions panel (8) | Done |
| Add tank (code, fuel, capacity default 10000, opening stock, calibration), manage-only | Done |
| Tank detail: summary, six actions disabled without manage | Done (disabled with an explanation) |
| Transactions / Readings / Reconciliation tables | Done |
| Variance bar card for the latest reconciliation | **Partial**: text summary + classification badge, no bar graphic |
| Receipt, Issue, Adjustment (negative allowed, reason required) | Done |
| Record reading (employee, physical, dip, remarks) | Done |
| Reconcile (date, physical, remarks) + result message | Done |
| Change status with reason | Done |
| Enter moves to next field, last field submits | Done (shared helper, tested) |
| Same permissions (inventory.view / inventory.manage / employee.view) | Done, enforced by the services |
| Audit rows for every change | Done (asserted per endpoint, chain verified) |
| Duplicate-instance bug | Fixed by design; proven by unit and e2e tests |

## Employees parity checklist (Qt `employee_window.py` vs new UI)
| Qt feature | New UI |
|---|---|
| Searchable list (name / code), columns code, name, designation, department, status, joining date | Done |
| Status changed inline in the list row, reason required, cancel changes nothing, disabled without employee.manage | Done |
| Add employee (10 fields, outlet default "Main Outlet", joining date today), server field errors beside the field | Done |
| Detail: profile (contact, designation, department; blank designation/department clears), status + Apply, Record exit (today, reason) | Done |
| Documents: add via file dialog + type, remove with reason | Done (path comes from the one new bridge method files.pickPath) |
| Add / edit controls hidden or disabled for view-only roles | Done, server re-checks |
| Audit rows for every change | Done (API tests, chain verified) |

## Parity of the screens built after Employees
Each screen was built from its Qt window's code (fields, defaults, permissions, messages) and calls the same service methods. Per-screen detail, judgment calls and tests are in `JS_MIGRATION_LOG.md`; the table below is the one-line status per Qt window.
| Qt window | New UI |
|---|---|
| Fuel Prices, Users, Nozzles & Dispensers, Suppliers / Procurement (orders, deliveries, invoices, payments) | Done |
| Shifts, My Shift, Attendance, Leave | Done |
| Sales + Customers, Sales Terminal (live preview in exact decimals), Credit (accounts, payments, statements) | Done |
| Expenses (+ categories), Reconciliation, Shift Cash Book, Employee Shortages | Done |
| Reports hub (12 reports, filters), Business Insights (performance, forecast), print preview, PDF / Excel / CSV | Done |
| Dashboard, Alerts, global search, account menu, lock screen, PIN, forgot password, Support, Hindi / English sign-in | Done |
| Company Profile, Backups (create, check, copy off-device, restore), Audit Log (filters, verify trail) | Done |
| Windows Hello on the lock screen | NOT done (needs a native Windows module); password or PIN always works |
| Printing to real paper / thermal hardware | NOT verified (no printer on the build PC) |

## UX improvements (reasons in the log)
Card shortcuts (Receipt / Record reading), detail as a route, level shown in words and icon, inline validation with server field errors, current stock shown in dialogs, remembered reader, reconcile result, cards/table toggle, outside clicks never discard a form, one no-access message, disabled buttons explain why.

## Printing findings
- The Qt app already builds its printable documents as HTML (`build_table_report_html`, `build_sale_receipt_html`) and its PDF/Excel/CSV exports in Python (ReportLab / openpyxl). Both carry over unchanged: HTML goes to the Electron print helper, files stay a server job.
- Verified from the Electron app, using the real Qt HTML builders: A4 report to PDF (2 pages, text extractable, correct size) and 80 mm receipt to PDF (1 page, 227 x 454 pt, content correct).
- Silent print to the system default (this PC has only "Microsoft Print to PDF" and OneNote): the call returned success, but no file or job appeared, because that driver always asks for a filename. **Silent printing to a physical printer is NOT verified.** Electron also reported no printer as default although Windows has one; the helper falls back to the system default.
- Thermal receipt printers: most Windows drivers accept the same GDI route with a custom page size (80 mm, long roll) and zero margins, so the HTML receipt should work, unverified without hardware. Cutter, cash-drawer kick and raw ESC/POS need raw bytes written to the printer (a small Node module or `copy /b`), which Chromium printing cannot do. Qt's print preview has no equivalent yet; it would be built in the web UI.
- Fixed while testing: custom page sizes are microns for `print()` but inches for `printToPDF()`; the PDF output path can only be chosen by the test harness, never by the page.

## Measurements (this PC, 5 runs each, warm file cache)
| | New app (Electron + Python API) | Existing Qt app |
|---|---|---|
| Installer | 131.7 MB NSIS (installed 417 MB) | no installer built locally (Inno Setup absent); the exe it wraps is 111.2 MB |
| Start to first window | **median 1.9 s** (1.8-2.1) | **median 9.4 s** (9.3-10.5) |
| Idle memory, working set / private | 429 MB / 253 MB, 5 processes | 242 MB / 194 MB, 2 processes |

Caveats: not a cold boot; the Qt number includes one-file unpacking; an Inno installer would be a little smaller than the exe. The new app starts faster, is larger on disk, and uses more memory (about 1.8x working set). The frozen API sidecar alone is 50 MB with no Qt inside.

## Honest assessment
Harder than expected:
- The sidecar is a second program to keep alive: ports, secrets, crash recovery, WAL checkpoint on quit, process-tree kill.
- Environment traps: this shell sets `ELECTRON_RUN_AS_NODE=1`; the installed sidecar fails if the install path is very deep (a migration filename reached 266 characters; a normal per-user install is about 180, so headroom is about 80 characters).
- Bugs my own tests caught in new code: the error window ordering made the whole app quit on a service crash; a double-click dismissed a dialog; a wrong `aria-describedby`; page-size units.
- Library bundles contain URL-like strings, so the offline gate needs a tiny exact allowlist.

Per-screen cost for the remaining ~25 screens: the foundation (API pattern, shell, table, forms, dialogs, tests) now exists, so a typical list + form screen is roughly 1-2 days including API tests, UI, unit and e2e tests; heavy screens (Terminal, Shifts, Reconciliation, reports with print preview, Settings/Backups) 3-5 days each. Roughly 8-10 weeks of one developer overall, plus a print-preview component and a file-download path through the API. This is an estimate, not a measurement.

Risks, and does the Electron decision hold? Yes for printing control, rendering consistency and start time. The costs are install size, memory, a larger surface to keep patched (Electron updates), and two toolchains (Python and Node) in builds. No CI job exists yet for web or desktop, and the release workflow still builds only the Qt app. Tauri would not remove the sidecar and loses print control, so the decision stands; memory on old pump PCs should be tested.

## NEEDS HUMAN REVIEW
- Nothing was changed in RBAC meaning, AuditLog, backups or migrations.
- Policy choices to confirm for every migrated screen: the API enforces the forced password change server-side (Qt only in the UI); it rejects deactivated users mid-session; request decimals finer than 3 places are rejected rather than rounded; the fuel lookup requires inventory.manage.
- `describe_unexpected_error` is duplicated in `api/errors.py` because the original imports Qt; moving it to `app/core` would remove the copy (not done: out of scope).
- The sidecar and the Qt app use the same database file by default; running both against live data at once is untested.
- `requirements.lock` changed (typing_extensions 4.15.0 to 4.16.0, new API packages with hashes).
- Dip value 0: Qt treats 0 as "not entered"; the new UI sends 0 as 0.

## Deferred / not done
PIN sign-in, Windows Hello, screen lock, self-service reset, locale toggle, Caps Lock warning, lockout countdown, code signing (installer is unsigned and uses the default icon), auto-update, variance bar graphic, silent print to a physical printer, CI for web/desktop, Qt-style print preview, trimming Electron locales to cut size.

## Screenshots
`docs/js-login.png`, `docs/js-tanks.png`, `docs/js-tank-detail.png`, `docs/js-tanks-dark.png`.

## Run it
`web`: `npm install && npm run build`. `desktop`: `npm install`, then `npm start` (unset `ELECTRON_RUN_AS_NODE` first). Tests: `npx vitest run` in each; `npm run e2e` in `desktop`.

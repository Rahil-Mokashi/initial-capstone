# JS Migration Log

Running log of the Qt -> Electron/React migration (proof screen: Tanks).
Branch `feature/js-frontend`. Never pushed.

## Phase 0 - reset point (2026-10-09)
- Tree clean on `feature/login-screen-enhancements` @ `652c589`.
- Baseline full suite: **996 passed** (brief said 993; the suite grew). Took 5m20s, not ~23 min; no hang this run.
- Tag, bundle (verified okay), DB and exe copies, branch, `RESET_POINT.md`: done. See that file.
- Not touched: `%LOCALAPPDATA%\PetrolPumpERP\` (installed app's DB, may be real data).
- Commit style follows git log (`docs:`, `feat:`...). No attribution trailers on commits (owner's preference for this repo).

## Phase 1 - ADR
- `docs/adr-js-frontend.md` written. Judgment calls recorded there (per-request DB session,
  `describe_unexpected_error` equivalent without Qt, shared DB with the Qt build).

## Phase 2 - API layer
- Dependencies: fastapi 0.143.0, uvicorn 0.54.0 (+ starlette 1.7.0, anyio, h11, click, idna, annotated-doc,
  opentelemetry-api) added to requirements.txt, pyproject.toml and the HASH-PINNED requirements.lock
  (hashes fetched from PyPI; `pip install --dry-run --require-hashes -r requirements.lock` passes).
  The lock's `typing_extensions` moved 4.15.0 -> 4.16.0 because fastapi's closure pulled it in (global env).
  The installed fastapi was 0.104.1 / starlette 0.27, which is incompatible with the installed httpx 0.28
  test client, hence the upgrade. Starlette's TestClient prints a deprecation warning about httpx
  (it prefers httpx2); harmless today, watch on upgrades.
- Package `api/`: app factory, launch-secret dependency, per-request DB session, current-user
  dependency (AuthService.validate_session), error envelope, schemas, auth + tanks routers,
  health + graceful shutdown, `main.py` sidecar entry (loopback-only, WAL checkpoint on exit),
  `export_openapi.py` for type generation.
- Routes call the SAME TankService/EmployeeService/AuthService/UserService methods as the Qt Tanks window;
  no `*_as_related_action`. Permission checks stay in the services.
- Judgment calls:
  * Per-request Session instead of Qt's single long-lived one (thread safety); same repos/constructors.
  * `describe_unexpected_error` re-implemented in api/errors.py (Qt version imports PySide6).
  * Request decimals must be JSON STRINGS with <= 12 digits / <= 3 places (the Numeric(12,3) column). Anything
    finer is rejected with 422 instead of being silently rounded by the database.
  * `/api/lookups/fuels` (Qt reads FuelRepository.list_active() unchecked, but only shows the dialog to
    INVENTORY_MANAGE users) is gated on INVENTORY_MANAGE through AuthService.check_permission + audit of denial.
  * Forced password change: Qt enforces it only in the UI. The API additionally returns 403
    `password_change_required` for everything except /auth/* until the password is changed (the seeded
    admin has the flag set, so login alone would otherwise be a bypass of the Qt behaviour).
  * Only the Qt screen's three transaction types (receipt/issue/adjustment) are accepted.
  * `fill_percent`/`is_low` are computed server-side (same clamp as app/ui/widgets.stock_percent and the
    DASHBOARD_LOW_STOCK_THRESHOLD_PERCENT constant) so the browser does no arithmetic on stock.
  * Session user deactivated mid-session: Qt does not re-check `is_active` on validate_session; the API
    does (401). Stricter than Qt, not looser.
- Tests: tests/api (107): every endpoint x {401 no token, 401 bad token, 403 missing/wrong secret};
  per-endpoint success, 403 (role without the permission), 422, 404/409 rules; AuditLog row asserted for
  every state-changing call and `verify_chain()` after; decimals-as-strings contract; loopback-only bind;
  Host header; CSP; no CORS; no docs endpoints; 500 mapping.
- Full suite after phase: **1103 passed** (996 baseline + 107 API), 8m08s, no hang.

## Phase 3 - Electron shell + front-end foundation
- `desktop/` (Electron 44.7, TypeScript strict, esbuild bundles main + two preloads) and `web/` (React 19, TS ~5.9 strict,
  Vite 7, Tailwind 4, TanStack Query 5 + Table 8, React Router 7 (HashRouter), react-hook-form + zod 4, Radix Dialog/Tabs,
  lucide, @fontsource-variable/inter). ESLint 9 + Prettier + `@/` path aliases in both.
- Version choices: npm "latest" is newer than I could vouch for (TypeScript 7, TanStack Table 9, ESLint 10), so I pinned
  the majors whose APIs I know (TS 5.9, Table 8, ESLint 9, Vite 7). Upgrading is a separate, deliberate task.
  `npm audit`: web 0 issues (vitest 5 fixed a tinypool advisory); desktop 8 moderate, all `sprintf-js` inside
  electron-builder (build-time tooling, never shipped) - left alone.
- Process lifecycle as in the ADR: free port, 32-byte random launch secret, env hand-off, health poll, single-instance lock,
  graceful shutdown first (`POST /api/system/shutdown`, sidecar checkpoints the WAL) then force-kill of the process TREE
  after a timeout, crash -> error window with "Try again". Proven by e2e (WAL file is 0 bytes after quit).
- Hardening as in the ADR: contextIsolation, no nodeIntegration, sandbox, no webview, deny new windows, block navigation,
  deny every permission request, preload exposes exactly {apiBase, launchSecret, print.{toPdf,toPrinter,listPrinters}}.
  Offline: CSP (layer 1) + `session.webRequest` blocker cancelling everything but the sidecar's own origin (layer 2,
  also rejects URLs with embedded credentials) + build gate (layer 3).
- UI is served BY THE SIDECAR (same origin, static files from web/dist), not loaded from file://. Reason: with
  `default-src 'self'` this needs no CORS at all and no `file://` special cases. Dev: Vite proxy adds the secret.
- Typed client: `npm run api:types` exports the OpenAPI schema from the FastAPI app and runs openapi-typescript;
  request decimals are typed `string` (WithJsonSchema) so the compiler also forbids sending numbers.
- Build gate `web/scripts/check-offline.mjs` runs inside `npm run build`. It first FAILED on inert strings inside bundled
  libraries (react.dev error-doc links, react-router doc link, JSON-schema dialect ids, an IPv6 template). Those are
  allowlisted EXACTLY, for .js files only; HTML/CSS get no allowance. Unit-tested incl. look-alike hosts.
- Tests: web Vitest 102 (error mapping, client, formatting, shared components, offline gate, WCAG contrast of both
  themes, Tanks flows); desktop Vitest 29 (request policy, sidecar lifecycle with a stub service).
- Bugs found by tests and fixed in NEW code (none in Qt/backend): `aria-describedby` pointed at a hidden hint when an
  error showed; closing the main window before opening the error window made Electron quit the whole app; a
  double-click on "Add tank" opened then instantly dismissed the dialog (outside-click now never dismisses a form).
- Environment trap: this machine's shell sets `ELECTRON_RUN_AS_NODE=1`, which makes `electron` run as plain Node.
  The sidecar launcher, the e2e fixtures and docs all unset it. Anyone running `npx electron` by hand must too.

## Phase 4 - Tanks proof screen
- Feature parity with `app/ui/tank_window.py` (see the checklist in JS_MIGRATION_REPORT.md): gauges + table + recent
  transactions, add tank, tank detail (transactions / readings / reconciliations + variance card), receipt / issue /
  adjustment, dip reading, reconcile (with result), change status (reason), all gated by the same permissions.
- UX improvements (each with its reason):
  1. Receipt and Record reading are buttons on each tank card - one click from the list instead of list -> detail -> button.
  2. Tank detail is a ROUTE, not a stacked dialog: Back works, the page can be reloaded, and it cannot be opened twice.
  3. Fill level is printed ("25.0%", "Low - 18.0%") next to the bar with an icon: never colour alone, readable at a glance.
  4. Inline validation next to each field (3-decimal limit, no negatives, reason required for adjustments) before anything
     is sent; the server's per-field errors are placed on the right field, and the typed values are kept on any failure.
  5. Dialogs show the tank's current stock so a wrong number is noticed before saving.
  6. Reading dialog pre-selects whoever took the last reading on this PC (localStorage; failure ignored).
  7. Reconcile starts with today's date and shows a clear result (expected / physical / variance / classification) before closing.
  8. Cards/Table toggle: Qt showed both at once; here one at a time, so the screen is less crowded.
  9. Outside clicks never dismiss a data-entry dialog (lost typing); Esc / Close / Cancel do.
  10. A role with no inventory access sees ONE explanation instead of an error in every panel.
  11. Disabled action buttons say why ("Needs the inventory.manage permission").
- Qt screen behaviours deliberately not copied: the duplicate-window bug (impossible here: one route per screen and one
  dialog state value); QInputDialog for status change (now a real form with a validated reason).
- Open questions (matching the Qt screen in the meantime): (a) Qt's reading dialog lists employees via EMPLOYEE_VIEW, so a
  role with INVENTORY_MANAGE but not EMPLOYEE_VIEW cannot choose a person - same here, with an explanatory message;
  (b) the Qt dip-value box treats 0 as "not entered"; here an empty field is "not entered" and "0" is sent as 0.
- Playwright (real Electron + real Python API + seeded temp DB): 28 tests run by default + 3 opt-in - login, view, reading, receipt incl. rule
  violation, reconcile, accountant view-only, server-side 403 via the real stack, attendant no-access, logout and
  server-side token rejection, no duplicate module/window, offline (session makes zero non-loopback requests; page CSP;
  CSP-free window still blocked by the main-process blocker; main-process fetch blocked; blocker log asserted),
  hardening (no require/process, bridge keys, web preferences, new window/navigation denied, strict CSP, secret needed),
  single-instance lock, graceful WAL checkpoint, crash -> error screen -> recovery, un-startable service -> error screen.

## Deferred (per brief)
PIN sign-in, Windows Hello, screen lock, self-service reset, locale toggle, Caps Lock warning,
lockout countdown, code signing, auto-update.

## NEEDS HUMAN REVIEW
(none yet)

## Phase 5 - printing + packaging
- Printing spike, sidecar spec (api/pperp_api.spec, onedir, no Qt, 50 MB), NSIS installer (131.7 MB), installed-app smoke test and measurements: see JS_MIGRATION_REPORT.md.
- Late parity fix: Enter moves to the next field (as in the Qt screens); remarks are single-line like Qt.
- Final: Python 1103 passed; web 104; desktop 29; Playwright 28 (+3 opt-in).

## FIX BATCH (2026-10-09, after the proof phase)

### Step 0 - reset point re-verified (read-only)
Tag reset/pre-js-frontend-2026-10-09 resolves to 652c589 (matches RESET_POINT.md); feature/login-screen-enhancements is still 652c589; git bundle verify: okay; tree clean. The local history rewrite (removing a stray tool-name mention from my own new commits) touched only commits after b945d1d; the tag and original branch are unaffected.

### Fix 1 - install path length
- Before: longest relative path 152 chars (a stale __pycache__ .pyc inside alembic/versions; the longest .py that is actually loaded was about 127). Layout was resources\sidecar\pperp-api\_internal\...
- Changes (bundle layout only, migration file names untouched): PyInstaller contents folder "_internal" -> "_" (contents_directory in api/pperp_api.spec); stale __pycache__ dropped from the bundled data; extraResources folder resources\sidecar\pperp-api -> resources\api; NSIS default install folder %LOCALAPPDATA%\PPERP (33 chars here, set only when there is no previous install, via build/installer.nsh).
- After: longest relative path 107 (a third-party lxml .xsl file; the longest migration .py is about 105).
- Build gate (desktop/scripts/after-pack.cjs): measures the packed app, writes resources\path-budget.json, FAILS the build above 130. Justification: install folder + relative path must stay under 240 (260 minus 20 spare), so 130 allows an install folder of 110 characters; the default is 33.
- Startup preflight (desktop/src/preflight.ts, wired in main.ts): install dir + recorded longest path > 240 shows the error screen (what, the numbers, how to fix) and does not start the service. 4 unit tests.
- Verified: installed to a 166-char folder -> installer fine, app showed the too-long message, 0 sidecar processes (opt-in test e2e/deep-path.spec.ts passes); installed to the default folder -> packaged smoke test passes (login visible 3.7 s on this run).
- Note: the bundle also contains packages that are not needed by the API (lxml, mypy, psutil, setuptools, yaml) because they are installed globally on this machine; excluding them would shrink it further. Not done (out of scope).

### Fix 2 - Electron fuses
- @electron/fuses applied in desktop/scripts/after-pack.cjs: RunAsNode off, EnableNodeOptionsEnvironmentVariable off, EnableNodeCliInspectArguments off, EnableEmbeddedAsarIntegrityValidation on, OnlyLoadAppFromAsar on. Read back from the built exe with `npx @electron/fuses read --app <exe>`: all five as set.
- UI loading check: the UI is served by the sidecar over http://127.0.0.1 (not file://); only the error screen uses the file protocol and it lives inside app.asar, so OnlyLoadAppFromAsar is compatible. GrantFileProtocolExtraPrivileges (default on) was NOT changed: the brief did not list it and turning it off could affect the error screen; worth a look later.
- The asar integrity fuse needs the digest embedded in the exe, which electron-builder only writes when resource editing is on. Config changed from signAndEditExecutable:false to signAndEditExecutable:true + signExecutable:false (still no signing; it worked here without extra downloads).
- Consequence: the Node inspector is off, so Playwright's Electron mode cannot drive the INSTALLED build. The installed-app tests (e2e/packaged.spec.ts) now start the exe and attach over Chromium's --remote-debugging-port instead. Dev/e2e tests (unfused node_modules Electron) are unchanged.
- Verified on the INSTALLED build (4 opt-in tests, all passed): smoke (login, Tanks, receipt, graceful quit, WAL checkpointed, service gone); ELECTRON_RUN_AS_NODE=1 with -e "console.log(...)" does not run as Node (the control, an unfused dev Electron, does print it, proving the hazard); --inspect opens no inspector socket and a bad NODE_OPTIONS does not affect startup; offline rules still hold (outside fetch blocked, CSP header, bridge keys, no require/process).
- Manual: copied the unpacked app, changed one byte inside app.asar, launched: the app aborted (exit code -2147483645) and the service never started. So integrity validation works.
- A harness bug found on the way: a failed packaged test left the app running and polluted the next one; tests now always force-stop what they started.
- Offline build scan re-run: passed.

### Fix 3 - input scale on the Tanks forms
- New web/src/lib/decimalGuard.ts (pure rules) and components/ui/DecimalField.tsx. Every number box on the Tanks forms (capacity, opening stock, quantity, physical stock, dip value) now refuses an edit that would give more than 3 decimal places, more than 9 whole digits, letters, a second point, or (except for stock adjustments) a minus sign. The refused edit is undone AS A WHOLE and an explanation appears under the box ("Litres can have at most 3 decimal places (for example 1250.500). Extra digits are not accepted."). Nothing is rounded or trimmed; a pasted value that is too precise is refused whole. The same component takes maxFraction=2 for money fields in later screens.
- The server still rejects too-precise values (unchanged); the submit-time check stays as a backstop.
- Design note: React's onBeforeInput is not the browser beforeinput event, so the first attempt did not work; the guard now works in onChange (undo to the last valid text), which also covers paste, drag and mobile keyboards. Small trade-off: when an edit is undone the caret jumps to the end.
- Tests: web 134 (was 104): rule unit tests, component tests (4th place refused and explained, explanation clears, money 2 places, letters/second point, paste refused whole, minus only for adjustments, typing over a selection), two Tanks flow tests; one Playwright test types 12.3456 into a receipt, sees 12.345 plus the explanation, records it and sees the exact 2,512.845. The old unit test that expected the submit-time error for a 4th place was rewritten because the guard now prevents that state (its intent, no server call, is kept).

### Fix 4 - variance bar
- Read first (app/ui/widgets.py: variance_bar_fractions, _VARIANCE_COLOR_TONE, VarianceBarCard): two bars, Book (expected) and Physical (dipped), each a fraction of the LARGER of the two (negatives clamped to 0, both 0 -> empty); ONE colour for both bars from the classification: normal = neutral ink (light in dark mode), warning and investigation_required = amber, approval_required = red; a classification tag; "Variance: +/-X L (+/-Y.YY%)" line. The 0.5 / 1 / 2 % thresholds live in the backend (classify_variance); the UI shows the server's classification and does NOT re-derive it.
- New: web/src/lib/variance.ts (tone map + fractions on exact strings via BigInt), features/tanks/VarianceBars.tsx used on the reconciliation tab (replaces the text summary). Numbers are printed beside the bars, the classification is named in a badge with an icon, the figure has an aria-label stating every number and the class, each bar is a labelled meter. Colours are the theme tokens (--text, --warn, --danger), so light and dark both work.
- Tests: web 153 (+19): tone map incl. unknown fallback, fractions (equal, zero, negative clamp, exact strings), component (label, printed numbers, meters, widths, colour token per classification, plus sign).
- Screenshots: docs/js-variance-warning.png, js-variance-critical.png, js-variance-critical-dark.png (real app).
- Small difference from Qt, deliberate: bar fills use the same palette tokens as the rest of the web UI rather than the Qt hex values.

### Fix 5 - printing test harness (hardware needed; NOT verified)
- desktop/scripts/print-test/ (launcher run.cjs, main.cjs, static sample report.html and receipt.html generated from the real Qt HTML builders so the owner needs no Python). `npm run print-test -- --list | --printer "<name>" [--doc report|receipt|both] [--dialog] [--receipt-width-mm N] [--receipt-height-mm N] [--margins none|default] | --to-pdf <folder>`. Writes print-test-log.txt with exactly what Electron answered per job; the log itself says success only means "handed to the spooler".
- PRINTING_TEST.md: owner steps, an A4 checklist and a thermal-receipt checklist (driver vs raw, page size, margins, length, cut, density, drawer, rupee sign), and what to send back.
- What I ran here (no physical printer exists on this PC): --list (2 printers: OneNote, Microsoft Print to PDF), --to-pdf dry run (report: 2 pages, 595 x 842 pt; receipt: 1 page, 227 x 454 pt, text present), a bad printer name (exit code 2, clear message). Printing to paper: NOT done, NOT verified, and the silent Print-to-PDF driver is deliberately not used as evidence.
- Bugs found in the harness while testing it: Electron quits when the last hidden window closes (needed a window-all-closed handler); load errors are now logged instead of an unhandled rejection.

### Fix 6 - dependency and build checks
- requirements.lock vs the reset tag: 37 -> 46 pins. ADDED (exactly FastAPI/uvicorn's tree, all hash-pinned): fastapi 0.143.0, starlette 1.7.0, uvicorn 0.54.0, anyio 4.14.0, click 8.3.2, h11 0.16.0, idna 3.10, annotated-doc 0.0.5, opentelemetry-api 1.45.1. REMOVED: none. CHANGED: none.
- This FIXES an earlier side effect: the first lock bumped typing_extensions 4.15.0 -> 4.16.0 (pip pulled it in because anyio 4.15.x requires it). anyio is now pinned to 4.14.0, which does not need the newer typing_extensions on Python 3.13, and typing_extensions is back at 4.15.0 (the Qt app's original pin). `pip check` is clean and `pip install --dry-run --require-hashes -r requirements.lock` reports no conflict.
- Qt build from this branch: `pyinstaller petrol_pump_erp.spec` (output to a scratch folder so dist/ was not touched) built in 4m50s: 116,634,062 bytes (the earlier exe was 116,634,823). Launched on a fresh throwaway database: window "FuelDesk - Sign In" appeared after 12.8 s, database created. No Qt source or spec was changed.
- Qt tests: run in the final full suite (see below).

### Fix 7 - repeatable checks and docs
- OFFLINE_ACCEPTANCE.md created (did not exist): install, disconnect every network, sign in, view tanks, record a reading (or a receipt on an empty database), log out, restart. It states plainly that I could NOT do this step: it needs a real PC with the network physically off.
- desktop/README.md documents every script. npm scripts added (via scripts/opt-in.cjs, which also unsets ELECTRON_RUN_AS_NODE): test:packaged [--install], test:deep-path (self-installs into a deep folder), test:screenshots, test:print-spike, plus print-test.
- Each run once through npm:
  * test:packaged --install: 4 passed (smoke, run-as-node fuse with unfused control, inspector/NODE_OPTIONS, offline rules).
  * test:deep-path: first run FAILED (timeout). Cause: that spec still used Playwright's Electron mode, which the fuses (Fix 2) disable; the test, not the product, was wrong (the error window with the "too long" message did appear). Rewrote it to attach over Chromium's debugging port via shared e2e/installed.ts; then 1 passed. The test's expectations about the message were not loosened.
  * test:screenshots: 2 passed (docs regenerated).
  * test:print-spike: the call returned ok:true against "Microsoft Print to PDF" but nothing printed, i.e. it was a meaningless pass. The test now skips itself as INCONCLUSIVE when only virtual printers exist (not counted as a pass).
- Refactor note: shared installed-app helpers moved to e2e/installed.ts; packaged tests re-run after the move: 4 passed.

## CHECKPOINT - full migration, started (stopped by request)
The owner asked for ALL functionality to be migrated, in my preferred (dependency) order. Work began and was stopped after the first screen's backend and the shared toolkit. Everything below is committed and green; nothing else is half-done.

### Done and committed at this checkpoint
- tests/api/test_api_route_matrix.py: reads the OpenAPI schema and checks EVERY route (existing and future) needs the launch secret (403) and a session (401, also for a garbage token). New routers cannot forget authentication.
- Employees API (api/routers/employees.py, 21 tests): list, get, create, patch (only sent fields), status change with reason, exit (date defaults to today like Qt), documents list/add/remove. Audit rows and chain verified. Registered in api/app.py.
- Shared web toolkit: FormDialog (Enter-to-next-field, errors inside, one dialog), ReasonDialog (confirm + required reason), PageHeader, SearchBox, api.patch, Reason type on the API side.
- Preload bridge extended by ONE method, files.pickPath() (Windows file dialog in the main process; the page only receives a path or null), needed because Qt stores the picked file path for employee documents. Bridge-key tests updated. E2E can set PPERP_E2E_PICK_PATH.
- web/src/features/employees/queries.ts (hooks for all employee calls); API types regenerated.

### NOT done yet (next steps, in this order)
1. Employees UI: list (search, inline status with reason), add dialog (outlet default "Main Outlet", joining date today), detail page (profile edit, status apply, record exit, documents add via files.pickPath / remove), nav entry + routes, unit + Playwright tests, then the Employees commit.
2. Fuel Prices; Users; Nozzles & Dispensers; Suppliers/Procurement (largest); Shifts + My Shift; Attendance; Leave; Sales + Customers; Terminal; Credit; Expenses; Reconciliation (+ cash book, shortages); Reports hub; Analytics; Dashboard + alert strip + notifications; Company Profile; Backups; Audit Log; login extras (PIN, forgot password, lock screen, support).
3. After each screen: update the parity checklist in JS_MIGRATION_REPORT.md, run the full suites, rebuild the installer.
Not re-run at this checkpoint: Playwright (the bridge-key expectations were updated but not executed) and the full Python suite (only tests/api employees and route matrix were run: 75 passed).

### Employees UI (2026-10-11)
- Added web/src/features/employees: EmployeesPage (list, search, inline status with reason, add dialog), EmployeeDetailPage (profile, status/exit, documents); routes /employees and /employees/:id; nav entry enabled. No change under app/ or api/.
- Judgment call: the detail profile edits only contact, designation and department, exactly like Qt, even though the API accepts more fields.
- Tests: web 162 (9 new), Playwright employees.spec.ts (add, status with reason, document via stubbed file dialog, exit) passes; tests/api 182 passed.
- NEXT: Fuel Prices, then Users, Nozzles, Procurement, ...

### Fuel Prices (2026-10-11)
- api/routers/fuel_prices.py (list, history, set rate; MoneyIn = strings, 2 dp), Services now wires every service like AppController (lazy, per request). web: FuelPricesPage (priced/unpriced badge, warning banner, change price with reason, per-fuel history), shared hooks in web/src/api/hooks.ts.
- Tests: tests/api 6 new, web unit 4 new, Playwright fuel-prices.spec.ts.

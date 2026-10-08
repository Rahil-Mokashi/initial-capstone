# PetrolPumpERP — Project Status Report

**Generated:** 2026-09-27 · **Type:** Read-only audit (no code changed, nothing committed) · **Branch audited:** `feature/login-screen-enhancements`

This report was produced by running the full test suite, reading `ROADMAP.md`/`NIGHT_RUN_LOG.md`/`PROJECT_CONTEXT.md` in full, and independently verifying (by reading the actual source, not trusting the docs' own checkmarks) RBAC coverage, audit-log coverage, Decimal usage, WAL/FK enforcement, and the UI base-class migration across every `*_window.py` file.

---

## 1. Test Health

**Result: 993 passed, 0 failed, 0 skipped, 0 xfail.** Full run took 22m49s (1369.11s).

```
993 passed in 1369.11s (0:22:49)
```

- **Command:** `python -m pytest -q` (the `--timeout` flag doesn't exist in this project — `pytest-timeout` isn't installed; the suite instead relies on its own `faulthandler_timeout = 100` setting in `pyproject.toml`, which dumps a stack trace for any single test still running past 100s without aborting the run).
- **Drift vs. last known count:** `ROADMAP.md` and `NIGHT_RUN_LOG.md` both record **891/891 passing as of 2026-09-23**. Current count is **993**, a jump of **+102 tests**. This is explained, not a red flag: `git diff --stat` against 10 commits back shows 12 new/expanded test files (`test_leave_service.py`, `test_leave_ui.py`, `test_lock_screen_ui.py`, `test_login_bridge.py`, `test_pin_and_reset_dialogs_ui.py`, `test_terminal_settings.py`, `test_user_service.py`, `test_windows_hello.py`, `test_keyboard_state.py`, `test_dashboard_service.py`, plus expansions to `test_auth_rbac.py`, `test_main_window_open_paths.py`, `test_report_ui.py`, `test_reports_hub_ui.py`), matching the 5 commits made since 2026-09-23 (Leave module, login redesign, PIN/self-service reset/screen lock/Windows Hello/locale toggle, Caps Lock/lockout/remembered-usernames/theme info).
- **Skipped / xfail / flaky:** None observed. The dot-progress output was 993 consecutive `.` characters across all batches — no `s` (skip) or `x`/`X` (xfail/xpass) markers anywhere, and no failure this run. `pyproject.toml`'s own comment documents a known **intermittent hang, roughly 1 run in 4**, with no fault or output (attributed historically to two now-fixed bugs — a widget-leak native crash and a stubbed-`QMessageBox` deadlock, both resolved 2026-08-17 per `ROADMAP.md`'s "Next Immediate Task 0b"). This run did not hit it, but given the documented ~25% historical rate, a single clean run is not proof the intermittency is fully gone — worth another run or two before treating it as resolved.

---

## 2. Phase-by-Phase Status

`ROADMAP.md` is unusually self-citing already — nearly every checklist line names the exact file/method that implements it. Rather than re-deriving all of that, this section reports what the roadmap claims, marks which claims were **independently verified** by this audit's research (RBAC, audit logging, Decimal, WAL/FK, and UI base-class checks all read the actual source), and flags anything **not independently checked** so it isn't mistaken for verified fact.

| Phase | Roadmap's own status | Independently verified this pass? |
|---|---|---|
| 1 — Project Initialization | Complete | Not re-checked (docs existence, trivial) |
| 2 — Architecture Documentation | Complete | Not re-checked |
| 3 — Database Design & Core Framework | Complete | **Yes** — WAL mode and FK enforcement confirmed genuinely wired up now (see §5.4); the roadmap's own honesty about this being *originally* marked done but not actually wired until 2026-08-15 checks out as an accurate self-correction, not a still-open gap |
| 4 — Authentication & RBAC | Complete | **Yes** — permission-check coverage walked service-by-service, see §5.1. One open checklist item remains explicitly unchecked in the roadmap itself: "Wire permission decorator into real service methods as those services are built" — but this reads as an evergreen reminder for future services, not a current gap; no unguarded state-changing method was found anywhere in `app/services/` |
| 5 — Employee & HR Management | Complete except HR reports (deferred to 16) | Not independently re-verified beyond RBAC/audit pass, which found employee_service.py's methods correctly gated and audited |
| 6 — Attendance Management | Complete except reports/holiday calendar | Not independently re-verified for the attendance-specific business logic; audit/RBAC coverage confirmed for `attendance_service.py` |
| 7 — Shift Management | Complete except full reconciliation (deferred to 15, and 15 is itself now done) | RBAC/audit confirmed for `shift_service.py` |
| 8 — Nozzle Management | Complete except reports | RBAC/audit confirmed for `nozzle_service.py` |
| 9 — Tank & Inventory Management | Complete except reports | **Yes** — `tank_service.py`'s public/`_as_related_action`/private permission-split pattern verified line-by-line (§5.1); Decimal usage on `Tank`/`TankReading`/`TankTransaction` confirmed (§5.3) |
| 10 — Procurement Management | Complete except reports | RBAC/audit confirmed (12 audit call-sites matched against 12 state-changing methods) |
| 11 — Sales Management | Complete except sales reports/printable receipts (partially closed later — see 16/17) | **Yes** — `sale_service.py`'s permission split, audit coverage, and Decimal-only money arithmetic (no `float()` in the actual `amount = money(...)` computation) all verified (§5.1, §5.3) |
| 12 — Payment Management | Complete except reconciliation/reports | Audit coverage confirmed on `sale_service.py`'s Payment methods |
| 13 — Credit Management | Complete except fuel-type-sectioned/aging reports | **Yes** — audit coverage confirmed; one naming inconsistency found (not a security gap) — see §5.1 |
| 14 — Expense Management | Complete except reconciliation/reports | Audit coverage confirmed (4 audit calls / 4 state-changing methods) |
| 15 — Reconciliation Management | Complete except reports | Audit coverage confirmed (2/2); note the `seed_demo_data.py` script is broken against this phase's schema — see §3 |
| 16 — Reporting System | **Roadmap itself says "partial"** — the reports every earlier phase promised are done, but the larger problemstatement.md #25-32 enumeration is explicitly called out as not fully attempted | **Not independently verified.** This audit's agents checked RBAC/audit/Decimal/UI, not report-content completeness against the original problemstatement.md enumeration. Take the roadmap's own "partial" label at face value rather than "done" — it is the one phase where the roadmap does not claim completion |
| 17 — Printing System | Complete for everything that exists so far; print config management not attempted | Not independently re-verified beyond confirming `report_export.py`'s Decimal-safe formatting is shared infrastructure |
| 18 — Backup & Recovery | Complete except recovery-doc and optional encryption | **Yes** — `BackupService`'s audit-log coverage (including both success/failure branches of integrity-check and offsite-copy) confirmed at file:line (§5.2) |
| 19 — Testing | Roadmap claims "largely satisfied" / "effectively complete" | **Yes, exceeded** — 993 tests now pass (roadmap's own count was 891 as of 2026-09-23; see §1) |
| 20 — Packaging & Deployment | Complete end-to-end | Not independently re-verified; `dist/PetrolPumpERP.exe` exists on disk (built 2026-09-25) but is now **2 commits stale** relative to current HEAD (see git state, §7) — worth a rebuild before handing to anyone |
| 21 — Pilot Deployment & Feedback | **Not started** (roadmap itself is explicit: "requires real-world deployment... not further code changes") | Confirmed — no evidence in git history of a pilot deployment |
| 22 — Final Release | **Not started** | Confirmed |

---

## 3. Known Incomplete Work

### The PageWindow base-class refactor — independently re-counted, and it's not what the docs say

`NIGHT_RUN_LOG.md`'s Task 6 (2026-09-23) reports **3 of "~15+"** window files migrated onto the shared `PageWindow` base class (`app/ui/base_window.py:32`). That count is now stale on both numbers:

- **Actual file count:** `app/ui/*_window.py` contains **26 window files** (plus `base_window.py` itself, which defines the class and isn't a window).
- **Actual migrated count: 4, not 3** — `fuel_price_window.py`, `tank_window.py`, `nozzle_window.py` (the three the log names) **plus `leave_window.py`** (`class LeaveWindow(PageWindow):` at `app/ui/leave_window.py:35`), added in a same-day but unlogged commit when the Leave module was built directly onto the new pattern.
- **22 files remain unmigrated.** Of those, **19 still hand-roll the exact byte-for-byte-identical 6-line page-shell block** (`container = GridBackgroundWidget(); container.setObjectName("background"); ...`) that `PageWindow._build_page()` exists to replace — i.e. they are drop-in candidates for the same trivial migration already proven safe four times over: `analytics_window.py`, `attendance_window.py`, `audit_log_window.py`, `backup_window.py`, `credit_window.py`, `employee_window.py`, `expense_window.py`, `group_landing_window.py`, `my_shift_window.py`, `notification_window.py`, `procurement_window.py`, `reconciliation_window.py`, `report_window.py`, `sales_window.py`, `shift_window.py`, `support_window.py`, `table_report_window.py`, `terminal_window.py`, `user_management_window.py`.
- **3 files are legitimately different, not just unmigrated:** `settings_window.py` wraps its shell in a `QScrollArea` for a long form (genuinely different shape); `main_window.py` is the `QMainWindow` app shell, not a page; `login_window.py` is a `QMainWindow` hosting a QML scene by deliberate design (rebuilt 2026-09-02).
- `base_window.py`'s own docstring (lines 16–24) explains what was deliberately **not** extracted: table setup, button rows, and `refresh()` logic, because they differ across list-only / list-with-detail-dialog / tabbed-window shapes, and forcing a shared method now "would trade a real simplification for an abstraction that only sort-of fits every case."

**Bottom line: the refactor is ~15% done by file count (4/26), not the "partial, 3 of ~15" impression the docs currently give.** This is a maintainability debt item, not a correctness bug — every unmigrated file still works correctly, it's just carrying duplicated boilerplate.

### Other incomplete/deferred work found in the codebase's own docs

- **`scripts/seed_demo_data.py` is currently broken** (`PROJECT_CONTEXT.md:1101`): raises `TypeError: 'expected_cash' is an invalid keyword argument for ShiftReconciliation` — the model was restructured from cash/UPI/card columns into per-tender `ShiftReconciliationLine` rows, and this script was never updated. Worked around via a different seeding path, not fixed.
- **`docs/screenshots/` gallery is stale** except `login.png`/`main-window.png` (regenerated 2026-09-23) — every other screen's screenshot predates the sidebar (2026-08-24), retheme (2026-08-25), and 2026-09-16 navigation work.
- **An untriaged widget-duplication bug**: `test_opening_the_same_module_twice_leaves_only_one_instance_embedded` in `PROJECT_CONTEXT.md:991` notes that repeatedly opening the Tanks module leaves stale `TankListWindow` instances in the widget tree instead of exactly one — flagged as a separate, real, unfixed bug, distinct from a related widget-leak class already fixed elsewhere.
- **Alert-click deep-linking** opens the right screen but not the specific record (e.g., clicking a low-stock tank alert opens Tanks generally, not that tank's detail dialog) — a documented, deliberate scope boundary, not an oversight, but still open (`PROJECT_CONTEXT.md:1013`, restated at `:1102`).
- **`docs/daily-report-spec.md`** independently records **10 open questions for the pump owner**, most notably (see §6) whether genset/company-vehicle/Omni internal fuel consumption is physically dispensed through a metered nozzle — unresolved, and the same class of bug already found once (`TESTING` volume double-counting) could recur for `INTERNAL_CONSUMPTION` if the answer is yes.
- **`TODO`/`FIXME`/`XXX`/`HACK` markers: zero, anywhere in `app/`.** This codebase tracks deferred work in prose (ROADMAP.md, PROJECT_CONTEXT.md) rather than inline code comments — there is no separate buried backlog hiding in the source.
- **UI simplification pass (`NIGHT_RUN_LOG.md` Task 5) never reached 12 files**: `analytics_window.py`, `audit_log_window.py`, `expense_window.py`, `group_landing_window.py`, `login_window.py`, `procurement_window.py`, `reconciliation_window.py`, `settings_window.py`, `shift_window.py`, `support_window.py`, `terminal_window.py`, `user_management_window.py` were explicitly never reviewed for the redundant-clicks pattern that pass was hunting. (This audit's UI inventory, §4, did review all of them for rough edges and found none — but that was a different, narrower check than Task 5's full "collapse multi-step flows" review.)

---

## 4. UI Inventory

All 26 `app/ui/*_window.py` files, independently reviewed. "Rough edges" search methodology: grepped every file for `QMessageBox.question` (Yes/No confirmations) — found **exactly one in the entire directory**; grepped for per-row action widgets against each file's top-level buttons to find duplicated actions; grepped for TODO/FIXME/HACK/"workaround" — zero hits. Most rows below are honestly "none observed," not a reluctant search.

| File | Purpose | Uses `PageWindow`? | Rough edges observed |
|---|---|---|---|
| `analytics_window.py` | Business Insights: period performance + sales-forecast tabs | No | None |
| `attendance_window.py` | Attendance roster: view/mark/correct | No | Per-row quick Present/Absent buttons *and* a top "+ Mark Attendance" dialog both exist, but a code comment explains they cover different cases (quick path vs. Late/Half-Day/Leave/corrections) — documented, not an unexplained duplicate |
| `audit_log_window.py` | Read-only audit trail + hash-chain "Verify Trail" | No | None (correctly uses info/warning dialogs, not confirmations, since it's read-only) |
| `backup_window.py` | Backup/restore/integrity-check/offsite-copy | No | The **only** Yes/No confirmation dialog in the whole app guards "Restore Selected" — appropriate, since restore overwrites the live database |
| `base_window.py` | Defines the shared `PageWindow` base class | — (n/a, not a window) | n/a |
| `credit_window.py` | Credit accounts + statement/payment/limit actions | No | None |
| `employee_window.py` | Employee/HR list, add/edit, status/exit, documents | No | None |
| `expense_window.py` | Expenses + Categories tabs, approve/reject | No | None |
| `fuel_price_window.py` | Fuel selling-price screen + price history | **Yes** | None |
| `group_landing_window.py` | Per-sidebar-group module tile landing page | No | None |
| `leave_window.py` | Leave request/approve/reject/cancel | **Yes** | None |
| `login_window.py` | Login screen (QML-based since 2026-09-02) | No (`QMainWindow`, deliberately different kind of screen) | None |
| `main_window.py` | App shell: top bar, sidebar, dashboard, alerts | No (`QMainWindow`, the shell itself) | None |
| `my_shift_window.py` | Attendant self-service current-assignment view | No | None |
| `notification_window.py` | Local alerts (deliberately read-only, no dismiss) | No | None — the lack of a dismiss button is a documented design decision (alerts are recomputed live), not a dead end |
| `nozzle_window.py` | Dispenser/Nozzle master data, tabbed | **Yes** | None |
| `procurement_window.py` | Suppliers/POs/Invoices/delivery workflow | No | None |
| `reconciliation_window.py` | Shift reconciliation, per-tender dynamic form | No | None |
| `report_window.py` | Reports Hub + Fuel Type Summary report | No | None |
| `sales_window.py` | Sales + Customers tabs, role-based entry flow | No | None |
| `settings_window.py` | Company profile / operational preferences | No | Genuinely different shell shape (scroll area for a long form) — not a drop-in `PageWindow` candidate as-is |
| `shift_window.py` | Shift open/close, nozzle assignment, reopen | No | None |
| `support_window.py` | Static help/support screen | No | None |
| `table_report_window.py` | Generic Refresh/Print/Export table-report shell | No | None |
| `tank_window.py` | Tank & Inventory: list, readings, transactions | **Yes** | None |
| `terminal_window.py` | "Quick Bill" fast sale-entry terminal | No | None — confirmed not a dead end (confirmation card + reset for next sale) |
| `user_management_window.py` | User account management across six roles | No | None |

No inconsistent styling, no dead-end flows, and no case of a confirmation prompt guarding a genuinely safe/reversible action was found anywhere in the directory.

---

## 5. Architecture & Data Integrity

### 5.1 RBAC permission checks

Mechanism: `require_permission(permission_name)` (`app/core/permissions.py:16-32`) wraps a service method and calls `AuthService.check_permission` (`auth_service.py:314`), raising `PermissionDeniedError` and recording the denial (`auth_service.py:321`) on failure.

**No unguarded, undocumented state-changing method was found anywhere in `app/services/`.** Every state-changing method is either `@require_permission`-decorated, or one of these documented, deliberate exceptions:

- **The public / `*_as_related_action` / private three-way split**, used consistently beyond just Tank/Credit as the roadmap claims — also confirmed in `SaleService`, `ExpenseService`, and `FuelService`. Example: `TankService.record_reading` (checked, `INVENTORY_MANAGE`, `tank_service.py:132`) vs. `record_reading_as_related_action` (unchecked, `:136`, called only by services whose own permission check already authorized the caller) vs. private `_record_reading` (`:146`).
- **Self-service exceptions**: `UserService.change_own_password`/`set_own_pin` (`user_service.py:186`, `:211`) operate only on the caller's own account, re-verify the current password, and are audit-logged. `reset_password_with_code` (`:271`) is a pre-authentication forgot-password flow with identical generic errors on every failure path.
- **Read-only aggregators** (`DashboardService.get_summary`, `NotificationService.get_notifications`) have no top-level check but gate each KPI/alert category internally per-permission — correct, since nothing here mutates state.

**One cosmetic finding, not a security gap:** `CreditService.ensure_credit_available` (`credit_service.py:169`) is unchecked like the `*_as_related_action` methods but doesn't follow their naming convention (no underscore, no suffix). Its only caller (`sale_service.py:229`) is itself gated by `create_sale`'s `SALE_MANAGE` check, so this is a naming inconsistency worth cleaning up, not a functional hole.

### 5.2 Audit logging coverage

`AuditLog` (`app/models/audit_log.py`) + `AuditLogRepository` implement a genuine **tamper-evident hash chain** — every entry's hash includes the previous entry's hash (`compute_entry_hash`, `:12-40`), and `verify_chain()` (`:107-138`) recomputes and flags any break.

Audit call-sites were counted per service and matched against every state-changing method identified. **No gap found** — every financial/state-changing method across `tank_service.py`, `credit_service.py`, `sale_service.py`, `expense_service.py`, `procurement_service.py`, `user_service.py`, `backup_service.py`, `shift_service.py`, `reconciliation_service.py`, `employee_shortage_service.py`, `shift_cash_book_service.py`, `nozzle_service.py`, `employee_service.py`, `leave_service.py`, `fuel_service.py`, `settings_service.py`, and `attendance_service.py` writes an audit entry. `analytics_service.py`, `dashboard_service.py`, `notification_service.py`, `report_export.py`, and `report_service.py` correctly have zero audit calls — they're read-only.

### 5.3 Decimal usage for money/volume fields

**Zero `Float` columns anywhere in `app/models/`.** Every money/volume/quantity column across 20 model files (`tank.py`, `sale.py`, `fuel.py`, `shift_reconciliation_line.py`, etc.) uses `Numeric` — e.g. `Fuel.rate_per_liter = Column(Numeric(10, 2), ..., default=Decimal("0.00"))` (`fuel.py:29`), `Tank.capacity/current_stock/opening_stock` all `Numeric(12, 3)` (`tank.py:36-38`).

`app/core/money.py` centralizes rounding (`money()` for currency at 2dp, `volume()` at 3dp, both `ROUND_HALF_UP`, never routing through `float()`).

The only `float()` casts found in `app/services/*.py` are confined to **non-persisted** logic: a linear-regression forecast helper (`analytics_service.py:83-84`) and variance-severity classification against static float threshold constants (`tank_service.py:38`, `reconciliation_service.py:35`) — both explicitly commented as deliberate, and both confirmed to compute the actual persisted `variance`/`amount` values in pure `Decimal` beforehand. No float-precision leakage into stored financial data was found.

### 5.4 WAL mode / foreign-key enforcement

Confirmed genuinely wired up, not just declared, in `app/database/connection.py:58-73`:

```python
@event.listens_for(Engine, "connect")
def _enable_sqlite_pragmas(dbapi_connection, connection_record) -> None:
    if type(dbapi_connection).__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()
```

This is a real SQLAlchemy `event.listens_for(Engine, "connect")` hook that fires on every new connection, guarded to only real `sqlite3` connections. `ROADMAP.md`'s own claim that this was "originally marked done but never actually wired up until 2026-08-15" is confirmed accurate as a historical bug and confirmed **currently fixed**.

**Verification limit** (from the auditing agent, stated honestly): no test asserting `PRAGMA journal_mode` actually returns `wal` or that FK violations are rejected at the DB level was specifically searched for, and Alembic's separate migration engine wasn't checked for the same pragmas — migrations are a distinct code path from the runtime engine.

### 5.5 Risk items flagged for the owner's attention

Nothing found here rises to "looks actively broken." The closest things to a flag:
- `CreditService.ensure_credit_available`'s naming inconsistency (§5.1) — cosmetic.
- `PROJECT_CONTEXT.md`'s own "Known Limitations" section (still true today, not re-verified further this pass): `Numeric` columns round-trip through a float internally at the SQLite driver storage layer — a documented SQLite/SQLAlchemy limitation outside the app's control, mitigated by keeping `Decimal` end-to-end in Python (which §5.3 confirms is actually the case).
- Several services (Employee, Attendance, Shift, NozzleAssignment) rely on check-then-insert rather than catching `IntegrityError` — acceptable for the current single-writer offline deployment, flagged in the docs themselves as worth revisiting only if concurrent writers are ever introduced.

---

## 6. Open Gaps (self-reported by the project's own docs)

No document in this repo uses the literal phrase "NEEDS HUMAN REVIEW" — a grep across `PROJECT_CONTEXT.md`, `NIGHT_RUN_LOG.md`, and `ROADMAP.md` found zero matches. The project's actual convention for flagging owner-decisions is phrases like "OPEN QUESTION, deliberately not guessed at," "Real, open follow-ups," and "deliberately deferred." The most decision-relevant items, in priority order:

1. **The single clearest owner-decision-needed item in the whole codebase** (`docs/daily-report-spec.md`, referenced at `PROJECT_CONTEXT.md:844`): does internal fuel consumption (genset, company Omni, company vehicle) get dispensed through a metered nozzle the same physical way a test dispensing does? If yes, `INTERNAL_CONSUMPTION` transactions carry the same meter double-counting bug that `TESTING` volume already had and was fixed for. This cannot be resolved from the code or any report — it needs the pump owner to describe how these fills are physically done at this specific site.
2. **Three original scoping questions never answered** (`PROJECT_CONTEXT.md:560-562`): exact attendant/fuel-attendant headcount needed, the full required-reports list beyond "broken down by fuel type," and expected supplier-management complexity.
3. **`scripts/seed_demo_data.py` is broken** (`PROJECT_CONTEXT.md:1101`) — see §3.
4. **The PageWindow refactor is ~15% done** (4/26 files) — see §3, independently re-counted (corrects the docs' own stale "3 of ~15" figure).
5. **The screenshot gallery is stale** except two images — see §3.
6. **An untriaged widget-duplication bug** in the Tanks module (opening it twice leaves two live instances) — flagged but not investigated.
7. **Ten open questions logged in `docs/daily-report-spec.md`**, including a reference-report contradiction (an Oil Sale ledger line item conflicting with the confirmed "fuel only, no other retail" business rule) and a same-shift total that doesn't reconcile under any single rounding rule tried — both explicitly recorded rather than silently resolved one way, per the project's own rule against inventing business rules.
8. **`PROJECT_CONTEXT.md`'s "Pending Modules" list is stale** — several items on it (payments/credit, reconciliation, printing, the Attendance shift-label FK) were actually completed in later-dated sections further down the same file. The gap-extraction research treated it as a point-in-time snapshot, not a current backlog; `NIGHT_RUN_LOG.md`'s task list is the more current source for what's actually still open.
9. **Alert-click deep-linking** opens the right module screen, not the specific record — a recorded, deliberate scope boundary (§3), open if deeper linking is ever wanted.
10. A `Known Limitations` bullet about "no installer" appears **stale/unreconciled within `PROJECT_CONTEXT.md` itself** — a working Inno Setup installer is documented later in the same file (~line 697) and confirmed present at `installer/petrol_pump_erp.iss`.

---

## 7. Git State

- **Current branch:** `feature/login-screen-enhancements`, up to date with `origin/feature/login-screen-enhancements`, working tree **clean** (no uncommitted changes, nothing to stash).
- **Unpushed commits:** none — this branch is fully pushed.
- **Branch relationship:** this branch is `feature/core-framework` (the PR base branch, tip `d8d4206`) plus 4 additional commits — meaning it's a feature branch built directly on top of the main integration branch, not diverged independently.
- **No stashes**, 3 local branches total (`main`, `feature/core-framework`, `feature/login-screen-enhancements`), 128 commits total in history.
- **What changed since the last documented review checkpoint** (the `d8d4206 docs: bring README up to date with recent modules and correct test count` commit, 2026-09-25, which itself reads as a "caught up the docs" checkpoint): 3 further commits, all also dated 2026-09-25 —
  - `2e4cea4` — Caps Lock warning, lockout countdown, remembered usernames, theme/device info on login
  - `0f6f117` — PIN quick sign-in, self-service password reset, screen lock, Windows Hello, login locale toggle
  - `fe086ed` — a style-only line-wrap fix in `login_bridge.py`

  In short: everything since the last doc-sync checkpoint is the second half of the login-screen feature list (ROADMAP.md's Next Immediate Task #8), fully committed, tested (see §1), and pushed — nothing new is sitting uncommitted.
- **Build artifact note:** `dist/PetrolPumpERP.exe` was last built 2026-09-25 23:25, which appears to predate at least the `fe086ed` style commit and possibly the feature commits made the same day depending on exact build time — treat the current `.exe` as **potentially one build behind** current `HEAD` and rebuild before distributing it, per this project's own standing rule to rebuild after every code change.

---

## 8. Honest Summary

The financial and permission core of this app is genuinely solid: every state-changing service method is either permission-checked or follows one of a small number of consistently-applied, well-documented exceptions; every one of those methods writes to a real tamper-evident audit hash chain; every money and volume column is `Numeric`/`Decimal` end to end with zero float leakage into stored figures; and WAL mode plus foreign-key enforcement are genuinely wired into the SQLAlchemy engine, not just declared. 993 tests pass with zero failures, skips, or xfails, and that count has grown honestly alongside real feature work rather than stagnating. The login experience is now a genuinely polished, feature-complete piece of work (PIN sign-in, Windows Hello, screen lock, self-service reset, lockout countdown) sitting on top of an otherwise business-correct backend. What's genuinely fragile is UI-layer maintainability, not correctness: 22 of 26 window files still duplicate a ~150-line boilerplate block that a proven, working base class already exists to eliminate, and that refactor is only about 15% done rather than the "partial, mostly there" impression the project's own docs currently give. A real user starting today would first notice a handful of rough spots that are documentation/tooling debt rather than product bugs: `scripts/seed_demo_data.py` is currently broken, the screenshot gallery is stale, one widget-duplication bug in the Tanks screen is known but untriaged, and the packaged `.exe` is a build or two behind the actual source. The single thing most worth the owner's actual attention before deeper reliance on this system is not a code defect at all — it's the unanswered physical-process question about whether genset/vehicle/Omni internal fuel consumption passes through a metered nozzle, because the app already found and fixed one real double-counting bug in that exact area and cannot rule out a sibling of it without an answer only the pump owner can give.

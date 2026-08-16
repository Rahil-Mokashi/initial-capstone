# Petrol Pump ERP - Project Context

## Project Objective
Build a complete Petrol Pump Management ERP capable of managing all petrol pump operations including fuel inventory, sales, procurement, HR, reporting, and more. The application is designed to be deployed on a petrol pump desktop computer and must operate reliably even when there is NO INTERNET CONNECTION.

## Business Understanding
A petrol pump management system needs to handle fuel inventory, sales, procurement, supplier management, employee management, shift management, fuel reconciliation, customer credit, and reporting. The system is a desktop-only application with SQLite database, capable of operating entirely offline.

## Current Architecture
- **Frontend**: PySide6 (Qt for Python)
- **Database**: SQLite (single file, zero-config)
- **ORM**: SQLAlchemy 2.x
- **Reports**: ReportLab for PDF, openpyxl for Excel
- **Packaging**: PyInstaller for desktop executable, offline deployment
- **Reporting**: ReportLab for reports
- **Packaging**: PyInstaller

## Database Design
- Single SQLite file (petrol_pump.db)
- UUID primary keys planned
- Foreign key constraints — actually enforced at the DB level via `PRAGMA foreign_keys=ON` on every connection (app/database/connection.py), not just declared in the ORM; see Known Bugs (Fixed)
- WAL mode enabled via `PRAGMA journal_mode=WAL` on every connection (same location)
- Proper normalization

## Completed Modules
- [x] Project initialization
- [x] Architecture documentation
- [x] Database connection module (app/database/connection.py)
- [x] Database base module (app/database/base.py)
- [x] Core models directory structure
- [x] User model (app/models/user.py) with proper fields
- [x] Role model (app/models/role.py)
- [x] Permission model (app/models/permission.py)
- [x] Fuel model (app/models/fuel.py)
- [x] User Repository (app/repositories/user_repository.py)
- [x] Fuel Repository (app/repositories/fuel_repository.py)
- [x] Auth Service (app/services/auth_service.py)
- [x] Inventory Service (app/services/inventory_service.py)
- [x] Core security (app/core/security.py) with password hashing
- [x] Configuration (app/core/config.py) with Pydantic v2 ConfigDict
- [x] Logging (app/core/logging.py)
- [x] Database initialization (init_db)
- [x] Initial data seeding (seed_initial_data) with admin user
- [x] MVP UI stub (app/ui/main_window.py) with PySide6 support
- [x] Core tests (tests/test_core_setup.py) passing
- [x] Git repository initialized with core framework commit
- [x] Roles/permissions constants (app/core/constants.py) — six business roles, baseline permission matrix, password policy, lockout threshold
- [x] Custom exceptions (app/core/exceptions.py) — AuthenticationError, AccountLockedError, SessionExpiredError, PermissionDeniedError, WeakPasswordError
- [x] Password policy validation (`validate_password_strength` in app/core/security.py)
- [x] Session token hashing (`hash_token` in app/core/security.py) — session tokens stored as SHA-256 hashes, not raw
- [x] AuditLog model (app/models/audit_log.py) — immutable, append-only, no update/delete
- [x] UserSession model (app/models/user_session.py) — tracks active sessions with expiry
- [x] `role_permissions` many-to-many wired between Role and Permission (was defined but never registered/used before)
- [x] AuditLogRepository, UserSessionRepository (app/repositories/)
- [x] Full AuthService rewrite (app/services/auth_service.py) — login/logout, session issue/validate/auto-expire, real RBAC permission checks, audit logging on every auth event, generic error messages (no username enumeration)
- [x] `require_permission` decorator (app/core/permissions.py) for service-layer authorization checks
- [x] seed.py now seeds all six roles and the baseline permission matrix, not just an admin user
- [x] Auth/RBAC test suite (tests/test_auth_rbac.py) — 13 tests covering login, lockout, permissions, session expiry, audit logging, password policy, the decorator
- [x] Login screen (app/ui/login_window.py) wired to AuthService — card UI, inline error banner, Enter-to-submit
- [x] Main window redesigned (app/ui/main_window.py) — top bar with username/role badge, Logout button, auto-logout via a 60s session-validity timer
- [x] AppController (app/ui/main_window.py) — owns the shared AuthService/DB session and the login <-> main window transition
- [x] Shared UI stylesheet (app/ui/styles.py) — consistent color palette, rounded inputs/buttons/cards, applied app-wide via QApplication.setStyleSheet
- [x] UI test suite (tests/test_login_ui.py) — 6 tests covering login window display, wrong-password/empty-field handling, successful login, logout, and auto-logout on session expiry
- [x] Employee model (app/models/employee.py) — HR master record, distinct from User (login account); exit tracked via status/exit_date, never deleted
- [x] EmployeeDocument model (app/models/employee_document.py) — soft-deletable document references (ID proof, etc.)
- [x] Pydantic validation schemas (app/schemas/employee.py) — EmployeeCreate/EmployeeUpdate with name/phone validation
- [x] EmployeeRepository, EmployeeDocumentRepository, RoleRepository (app/repositories/)
- [x] EmployeeService (app/services/employee_service.py) — create/update/status-change/exit/document management, all permission-checked (EMPLOYEE_VIEW/EMPLOYEE_MANAGE) and audit-logged
- [x] EMPLOYEE_VIEW/EMPLOYEE_MANAGE permissions added to the RBAC matrix (app/core/constants.py)
- [x] NotFoundError/ConflictError added to app/core/exceptions.py
- [x] Employee/HR test suite (tests/test_employee_service.py) — 16 tests covering creation, sequential employee codes, validation, permission enforcement, status/exit workflow, document add/remove, audit logging
- [x] Employee/HR UI (app/ui/employee_window.py) — EmployeeListWindow (searchable table), EmployeeFormDialog (add), EmployeeDetailDialog (edit profile, status/exit workflow with confirmation, document add/remove); "Employees" button added to MainWindow's top bar, hidden unless the user has EMPLOYEE_VIEW; manage actions (save/status/exit/documents) disabled for view-only roles
- [x] Employee UI test suite (tests/test_employee_ui.py) — 9 tests covering list display/search, permission-based visibility, add-employee validation, profile edit, status change, exit confirmation flow, document add/remove, manage-action disabling for view-only roles
- [x] AttendanceStatus enum (present/absent/late/half_day/leave/holiday) and ATTENDANCE_VIEW/ATTENDANCE_MANAGE permissions added to app/core/constants.py
- [x] Attendance model (app/models/attendance.py) — one record per employee per day (unique constraint); shift_label is free-text since the Shift entity doesn't exist yet (Phase 7); corrections tracked via correction_reason/corrected_by_id/corrected_at rather than a plain overwrite
- [x] Pydantic schemas (app/schemas/attendance.py) — AttendanceMark/AttendanceCorrection, validate check-out >= check-in and non-negative overtime
- [x] AttendanceRepository, AttendanceService (app/services/attendance_service.py) — mark_attendance (rejects duplicates via ConflictError) and correct_attendance (requires a non-blank reason, audit-logs old/new snapshot), all permission-checked
- [x] Attendance/HR test suite (tests/test_attendance_service.py) — 13 tests covering marking, duplicate rejection, permission enforcement, schema validation, the correction workflow, date-range/day filtering
- [x] Attendance UI (app/ui/attendance_window.py) — AttendanceWindow (date-filterable daily roster), AttendanceMarkDialog, AttendanceCorrectionDialog (requires a reason, manage actions disabled for view-only roles); "Attendance" button added to MainWindow's top bar, gated on ATTENDANCE_VIEW
- [x] Attendance UI test suite (tests/test_attendance_ui.py) — 7 tests covering visibility, date filtering, marking, duplicate rejection, correction reason requirement, and view-only disabling
- [x] Shared app/ui/qt_utils.py for QDate<->date conversion (extracted out of employee_window.py so attendance_window.py doesn't duplicate it)
- [x] Dispenser and Nozzle minimal master-data models (app/models/dispenser.py, app/models/nozzle.py) — just enough to give Shift's nozzle assignment something to point at; full Nozzle Management (CRUD/UI) is Phase 8
- [x] Shift model (app/models/shift.py) — one row per (shift_date, shift_label); open/close lifecycle; reopening records reason/who/when rather than silently flipping status
- [x] NozzleAssignment model (app/models/nozzle_assignment.py) — one attendant per nozzle per shift, opening/closing meter readings
- [x] SHIFT_VIEW/SHIFT_MANAGE/SHIFT_REOPEN permissions (reopening a closed shift is deliberately a stricter permission than routine open/close — SHIFT_SUPERVISOR gets manage but not reopen)
- [x] Pydantic schemas (app/schemas/shift.py) — ShiftOpen, NozzleAssignmentCreate, NozzleAssignmentComplete
- [x] ShiftRepository, NozzleAssignmentRepository, NozzleRepository, DispenserRepository
- [x] ShiftService (app/services/shift_service.py) — open_shift, assign_nozzle (rejects duplicate active assignment per employee/nozzle within a shift, rejects assignment to an inactive nozzle or a non-open shift), complete_nozzle_assignment (closing meter must be >= opening meter), cancel_nozzle_assignment (requires reason), close_shift (blocked while any assignment is still active), reopen_shift (requires SHIFT_REOPEN + a reason, audit-logged)
- [x] Shift/nozzle-assignment test suite (tests/test_shift_service.py) — 23 tests
- [x] Shift UI (app/ui/shift_window.py) — ShiftListWindow, ShiftOpenDialog, ShiftDetailDialog (assign/complete/cancel nozzle assignments, close, reopen); "Shifts" button added to MainWindow, gated on SHIFT_VIEW
- [x] Shift UI test suite (tests/test_shift_ui.py) — 6 tests
- [x] **Database integrity hardening**: SQLite foreign-key enforcement (`PRAGMA foreign_keys=ON`) and WAL mode (`PRAGMA journal_mode=WAL`) are now actually turned on for every connection via a SQLAlchemy `connect` event listener (app/database/connection.py) — previously neither was enabled despite CLAUDE.md/problemstatement.md explicitly requiring both, so every `ForeignKey()` in the models was documentation only and referential integrity was never enforced at the DB level
- [x] `safe_commit()` helper (app/repositories/base.py) — every repository's add/update now commits through it instead of calling `session.commit()` directly, so a failed write (e.g. a constraint violation) rolls back cleanly instead of leaving the long-lived per-login session's transaction aborted for every subsequent operation
- [x] `tests/test_database_integrity.py` — proves WAL mode and FK enforcement are actually active, that an invalid foreign key is rejected by the database, and that a session recovers after `safe_commit` rolls back a failed write (plus a documentation test showing the broken behavior without it)
- [x] `ShiftService.open_shift` now validates `supervisor_id` actually exists (`NotFoundError` otherwise) instead of allowing a dangling reference

## Current Module
Phase 9: Tank & Inventory Management is done end-to-end (service layer + UI, tested) — Tank master data, dip readings, transactions (receipt/issue/adjustment), and fuel reconciliation with configurable variance thresholds. Phases 4-8 (Auth & RBAC, Employee & HR, Attendance, Shift Management, Nozzle Management) are also done end-to-end. Database integrity (FK enforcement, WAL mode, safe commit/rollback) and end-to-end exception handling (startup failures, every UI action) have been audited and hardened across the whole app. The login screen and main-window dashboard were redesigned for a more eye-catching, minimal look (gradient hero panel, quick-access cards). The app can now also be packaged into a standalone Windows .exe (Phase 20 work, started early at the user's request — see Deployment Status). On top of the phase-9 baseline, three more user-requested features are done end-to-end: the attendant self-service "My Shift" view, fuel-type-sectioned (Petrol/Diesel/Power) tank & nozzle reports, and full User Management (create logins for any of the six roles, multiple users per role, activate/deactivate/unlock/role-change) — all gated by the same role-based `MainWindow` visibility pattern used everywhere else in the app, so what a logged-in user sees (top-bar buttons and dashboard cards) already automatically matches their role's permissions with zero extra wiring per screen.

On 2026-08-16 the user asked for a full build audit (published as an artifact) and then asked to resolve every item on its priority-ranked recommendation list. Nine of the ten were completed end-to-end (see the new entries below); the tenth — extracting a shared list-window/form-dialog base class to de-duplicate the ~150-line scaffold repeated across `app/ui/*_window.py` — was deliberately deferred rather than attempted as a large, risky refactor at the tail end of an already very large session; see Pending Modules.

- [x] **Alembic migrations are real** (top audit finding — CLAUDE.md requires "never modify database schema without migration" and "backup before migrations"): `app/database/migrations.py` wraps Alembic programmatically (`upgrade_to_head`, `has_pending_migrations`); `init_db()` now calls it instead of `Base.metadata.create_all()`, and a pre-migration backup is taken automatically whenever a launch detects pending migrations against a database that already has data. `alembic/` holds a baseline migration (`dacfb10de7de`) plus the `must_change_password` column migration. The PyInstaller spec now bundles `alembic.ini` + `alembic/` as data files so the frozen build can run migrations too.
- [x] **Money/volume columns moved from Float to Numeric/Decimal**: `Fuel.rate_per_liter`, `Tank.capacity/current_stock/opening_stock`, `TankReading.dip_value/physical_stock`, `TankTransaction.quantity`, `FuelReconciliation`'s six figures, `NozzleAssignment.opening_meter/closing_meter` — all `Numeric`, with matching Pydantic schemas typed `Decimal`. UI inputs (`QDoubleSpinBox.value()`) still work unchanged since Pydantic coerces float→Decimal via string conversion, avoiding binary-float artifacts.
- [x] **Resolved the Fuel/Tank stock-field redundancy**: removed `Fuel.capacity/current_stock/opening_stock` (Tank already owned this data since Phase 9) along with the dead, never-wired-in `InventoryService` that was the only code still reading them.
- [x] **Found and fixed a real latent bug while testing the above**: `TankTransactionRepository.sum_for_tank_by_type` compared a naive local-calendar-date boundary directly against `transaction_at` (stored UTC-aware), silently dropping transactions recorded after local midnight whenever local time runs ahead of UTC (this dev machine is IST, UTC+5:30) — fuel reconciliation could under-count same-day receipts/issues. Fixed by converting the day boundary to a UTC instant before comparing; the same fix was applied to the new `AuditLogRepository.search()`'s date filters pre-emptively. Two deterministic regression tests added (not relying on real-clock timing like the pre-existing test that first exposed this).
- [x] **Password self-service + forced rotation**: `User.must_change_password` forces a password change after any admin-set password (new account creation via `UserService.create_user`, or an explicit `UserService.reset_password` — new, closing the "a forgotten password has no recovery path" gap). `app/ui/change_password_dialog.py`'s `ChangePasswordDialog` is shown as an un-skippable step right after login when set (`reject()`/`closeEvent` both no-op in forced mode), and is also reachable any time via a new "Account" menu. The seeded default admin account is flagged too, so `Admin@123` gets rotated on first real use instead of staying in place silently.
- [x] **Production logging fixed**: `setup_logging()` now attaches a rotating file handler (`petrol_pump_erp.log`, 5MB × 5 backups) colocated with the database, since `console=False` in the packaged build means a console-only logger left no record at all on a client machine. While building this, found and fixed a much bigger, genuinely serious bug: Alembic's `env.py` calls `logging.config.fileConfig()`, whose `disable_existing_loggers` defaults to `True` — this was silently **disabling the app's own `petrol_pump_erp` logger for the rest of the process** every time `init_db()` ran migrations (i.e. on every startup), meaning the entire exception-logging safety net built earlier this session would have gone completely dark in production. Fixed with `disable_existing_loggers=False`.
- [x] **Backup/restore module**: `app/database/backup.py` uses `sqlite3`'s online backup API (not a raw file copy, which can miss data still sitting in a WAL file) for both manual and automatic pre-migration backups; `app/services/backup_service.py` adds RBAC (`Permission.BACKUP_MANAGE`) and audit logging, and takes its own safety backup before every restore so a bad restore choice is itself recoverable. `app/ui/backup_window.py` lists backups and lets an admin back up now or restore (with a required reason and a restart-required warning, since a running process's existing DB connections don't pick up a restored file on their own). Fixed a real filename-collision bug found while testing: two backups issued within the same second used to overwrite each other (second-resolution timestamps) — moved to microsecond resolution.
- [x] **Audit log viewer**: `Permission.AUDIT_VIEW` has been defined and granted to Manager/Accountant/Admin/Owner since Phase 4, but nothing ever checked it because there was no screen to view the trail on. `AuditLogRepository.search()` (event type / actor / date-range filters) + `app/services/audit_service.py` + `app/ui/audit_log_window.py` close that gap — every action any service already logs is now actually visible to the roles permissioned to see it.
- [x] **PDF/Excel export wired into the fuel-type report**: `app/services/report_export.py` (ReportLab for PDF, openpyxl for Excel — both declared as required stack since Phase 3 but never used until now) plus a native Print dialog (`QPrintDialog` rendering the same data as HTML via `QTextDocument`). Sets the pattern for the rest of Phase 16's reports to reuse.
- [x] **Universal Enter-key field navigation** (user-reported: pressing Enter after the username field submitted the login form directly instead of moving to the password field): new `chain_enter_to_next_field()` helper in `app/ui/qt_utils.py`, applied across every multi-field form in the app (login, change-password, user creation, employee add/edit, tank create/transaction, plus single-field forms wired to submit directly on Enter) so filling in a form with the keyboard alone advances field-by-field instead of submitting early.
- [x] **Dashboard/top-bar layout fixed** after growing to 10 modules: the dashboard card grid never actually wrapped rows (a pre-existing bug, `cards_grid.addWidget(..., 0, column)` always used row 0), so cards silently got squeezed and their text truncated once there were more than fit in one row — now wraps at 4 cards per row. The top bar's "Change Password" and "Logout" buttons were consolidated into a single "Account" menu to reduce clutter.
- [x] **CI**: `.github/workflows/tests.yml` runs the full suite on every push/PR via GitHub Actions (`windows-latest`, since this is a PySide6 desktop app whose tests assert on real Qt focus state — a Linux runner would need a virtual display and still behave differently for those specific assertions).

## Phase 10: Procurement Management (complete)
Full tanker-arrival-to-inventory-update workflow (problemstatement.md #12): Fuel Requirement -> Purchase -> Tanker Arrival -> Document Verification -> Fuel Quality Verification -> Pre-Dip Reading -> Fuel Unloading -> Post-Dip Reading -> Inventory Update -> Invoice -> Supplier Payment.
- [x] Models: `Supplier`, `PurchaseOrder`/`PurchaseOrderItem`, `FuelDelivery`, `SupplierInvoice`/`SupplierPayment` (`app/models/`), migration `be4e2b8f1220`
- [x] `ProcurementService` (`app/services/procurement_service.py`) deliberately depends on `TankService` (not just `TankRepository`) for the dip-reading and receipt-transaction steps — a delivery moves fuel into a tank through the exact same audited, capacity-checked path every other receipt does (`TankService.record_reading`/`record_transaction`), never a parallel one that could drift from it. This is exactly what PROJECT_CONTEXT.md predicted back in Phase 9: "Procurement will eventually create Tank RECEIPT transactions automatically from supplier deliveries."
- [x] Business correctness: a delivery's tank must match one of the PO's fuel types (rejected otherwise); the post-dip reading can't be recorded before the pre-dip, and can't be less than it; `quantity_received` is *derived* (post-dip minus pre-dip), never entered directly, so it can't drift from what was actually dipped; a PO's status (`PARTIALLY_DELIVERED`/`DELIVERED`) is recomputed from scratch from its deliveries every time, never incremented, so it can't drift out of sync either — same "recompute, don't accumulate" principle used for `SupplierInvoice.status`
- [x] `Permission.PROCUREMENT_VIEW`/`PROCUREMENT_MANAGE`, granted to Manager (full) and Accountant (view only, for the financial side)
- [x] `app/ui/procurement_window.py`: three tabs (Suppliers, Purchase Orders, Invoices); the delivery workflow lives inside the purchase-order detail dialog, with only the action valid for the delivery's current status enabled at a time
- [x] 30 service tests (`tests/test_procurement_service.py`) + 8 UI tests (`tests/test_procurement_ui.py`), including the full arrival-to-unload-to-tank-stock-update path end to end
- [x] Reserved and fully specified (not yet built at the time) Phase 13's Credit Management per explicit user requirements 2026-08-16: fuel-type-sectioned credit reporting, and every Sale must snapshot its own rate/amount at transaction time rather than a live `Fuel.rate_per_liter` lookup (fuel prices change over time) — see ROADMAP.md Phases 11/13 for the full detail, and Pending Modules below

## Phase 11: Sales Management (complete except sales reports/printable receipts, deferred to Phases 16/17)
- [x] Models: `Customer`, `Sale` (`app/models/customer.py`, `app/models/sale.py`) — `Sale.rate_per_liter`/`amount` are snapshotted at sale time per the user's confirmed requirement (fuel prices change over time), never a live `Fuel.rate_per_liter` lookup
- [x] `SaleService` (`app/services/sale_service.py`): `create_sale` validates the shift is OPEN, the nozzle is active, CREDIT sales require a `customer_id`; resolves which tank a nozzle's sale draws from via `_resolve_tank_id` (uses `Nozzle.tank_id` if set, else falls back to the single active tank for that fuel type, else raises `ConflictError` on real ambiguity); posts a real Tank ISSUE transaction via `TankService.record_transaction_as_related_action`; `cancel_sale` requires a reason, only works from COMPLETED, and posts a compensating ADJUSTMENT rather than ever deleting or overwriting the original sale
- [x] **Permission-layering bug found and fixed**: `TankService.record_transaction`/`record_reading` required `INVENTORY_MANAGE`, which blocked attendants (who only hold `SALE_MANAGE`) from ever completing a sale, since `create_sale` calls those methods as an internal side effect of an action the attendant *is* authorized to perform. Fixed by splitting each method three ways: the original permission-checked method (for direct callers), a new `*_as_related_action` unchecked twin (for calls a caller's own permission check already authorized), and a private `_impl` holding the shared logic. This pattern should be reused by any future service (Reconciliation, Expense) that triggers `TankService` side effects on behalf of a lower-privileged actor.
- [x] Added nullable `Nozzle.tank_id` (migration `211e22a49e32`, alongside the new `customers`/`sales` tables) since a pump can have more than one tank per fuel type and a sale needs to know which one it's drawing down; `NozzleService.create_nozzle` now validates a given `tank_id` exists and matches the nozzle's fuel type
- [x] `app/ui/sales_window.py`: `SalesWindow` (Sales/Customers tabs). `SaleFormDialog` branches on `SHIFT_VIEW` permission — Manager/Supervisor get full shift/nozzle/employee pickers, while an Attendant gets an auto-resolved read-only view of their own active `NozzleAssignment` (reusing `ShiftService.get_my_active_assignment` from the Phase 9 self-service work) so they never have to pick anything that isn't already true. "Sales" dashboard card added, gated on `SALE_VIEW`.
- [x] `Permission.SALE_VIEW`/`SALE_MANAGE` added; granted to Manager/Shift Supervisor (view+manage) and Accountant (view only), and to Attendant (view+manage, restoring the VIEW+MANAGE pairing convention used by every other role after a gap was found — Attendant initially only had `SALE_MANAGE`, which broke `SaleFormDialog`'s unconditional `list_customers()` call)
- [x] 16 service tests (`tests/test_sale_service.py`) + 5 UI tests (`tests/test_sales_ui.py`), plus new regression tests in `tests/test_tank_service.py` for the permission-layering fix

## Phase 12: Payment Management (complete except reconciliation workflows/reports, deferred to Phases 15/16)
- [x] Model: `Payment` (`app/models/payment.py`, migration `d948d120d0c7`) - a 1:1 satellite of `Sale`, tracked separately per problemstatement.md #17 since a sale's fulfilment (fuel dispensed) and its settlement (money collected) are related but distinct lifecycles
- [x] `PaymentStatus` enum (SUCCESS/PENDING/FAILED/REVERSED/REFUNDED) added to `app/core/constants.py`; `SaleService.create_sale` now also creates the linked `Payment` — SUCCESS immediately for cash/UPI/card, PENDING for credit (settled later via Phase 13); `SaleService.cancel_sale` now also reverses the linked payment (status -> REVERSED) as part of the same cancellation, never a separate silent step
- [x] `SaleCreate.reference_number` (optional) carries a UPI reference or card authorization code onto the payment; the sale form shows/hides that field based on the chosen payment method
- [x] New `SaleService` methods `mark_payment_failed`/`refund_payment` (both require a reason, audit-logged, gated on `SALE_MANAGE`) cover the after-the-fact correction cases explicitly named in the requirements (e.g. a card declines after fuel is already dispensed) — matching the project's VOID/REVERSE/ADJUST-not-DELETE rule for financial records rather than editing the original payment in place
- [x] `app/ui/sales_window.py`: the Sales table now shows a separate Payment Status column alongside Sale Status; "Mark Payment Failed"/"Refund Payment" actions added next to Cancel Selected, gated on `SALE_MANAGE`
- [x] Payment lives inside `SaleService`/`app/repositories/payment_repository.py` rather than a standalone service — it shares the exact same `SALE_VIEW`/`SALE_MANAGE` permission as Sale itself, at the exact same moments, so there's no permission-layering concern like the one `TankService` had (that fix applies when a *different* permission is involved)
- [x] 11 new service tests in `tests/test_sale_service.py` (payment created per method, credit starts pending, cancellation reverses it, failed/refund transitions and their guards, RBAC) + 2 new UI tests in `tests/test_sales_ui.py`

## Dashboard redesign (2026-08-16, user-requested)
The user explicitly said they didn't like the dashboard and asked for it to be "better placed" and enhanced. Changes, done in two passes:
- Dashboard cards are now grouped into two labeled sections ("Daily Operations": Employees/Attendance/Shifts/My Shift/Sales/Nozzles/Tanks/Procurement; "Reports & Administration": Reports/Users/Backups/Audit Log) instead of one flat, ungrouped grid — gives real visual hierarchy now that there are 12 modules.
- The top bar was decluttered down to just the username/role badge and a single "Account" menu (Change Password/Logout) — every module button that used to live there was redundant with its own dashboard card and was the direct cause of the top-bar button-crowding the build audit flagged. The dashboard is now unambiguously the one place to navigate from.
- **KPI strip** (added post-Phase 11, as part of the standing self-analysis/dashboard-enhancement pass): a row of at-a-glance stat tiles sits above the card groups — today's sale count/revenue, shifts open right now, tanks running low on stock (at or below `DASHBOARD_LOW_STOCK_THRESHOLD_PERCENT`, a flag not an alarm, matching the non-accusatory tone of reconciliation variance), and pending purchase orders. `app/services/dashboard_service.py` (`DashboardService.get_summary`) computes each figure gated on that module's own existing permission (`SALE_VIEW`/`SHIFT_VIEW`/`INVENTORY_VIEW`/`PROCUREMENT_VIEW`) and returns `None` for sections the acting user can't see — the UI (`StatCard` in `app/ui/main_window.py`) only renders tiles it actually received, so an Attendant's dashboard shows just their sales stat, nothing else. This turns the dashboard from pure navigation into something that actually surfaces what needs attention today, which is what "enhance it" was asking for beyond just visual tidying. 7 new tests in `tests/test_dashboard_service.py`.

- [x] PyInstaller packaging (`petrol_pump_erp.spec`, `requirements-build.txt`) — see "Deployment Status" for details and the two real bugs this surfaced (DB path under a frozen build, and a matplotlib/PySide6 hook interaction)

- [x] Tank, TankReading, TankTransaction, FuelReconciliation models (problemstatement.md #13/#14). Tank is distinct from Fuel (a fuel-type lookup already used by Nozzle) — a pump can have more than one tank per fuel type, each with its own capacity/stock; `Fuel.capacity/current_stock/opening_stock` are effectively superseded by `Tank`'s own fields and are a known redundancy left alone rather than changed without a migration path (no Alembic yet)
- [x] TankStatus/TankTransactionType/VarianceClassification enums and configurable reconciliation thresholds (`FUEL_VARIANCE_*_THRESHOLD_PERCENT`) in app/core/constants.py — reused the existing INVENTORY_VIEW/INVENTORY_MANAGE permissions (defined since Phase 3, never wired to a real feature until now) rather than adding new ones
- [x] app/schemas/tank.py: TankCreate, TankReadingCreate, TankTransactionCreate, ReconciliationPerform
- [x] TankRepository, TankReadingRepository, TankTransactionRepository, FuelReconciliationRepository
- [x] TankService (app/services/tank_service.py): create_tank, set_tank_status (reason required, audit-logged), record_reading (an observation — never silently changes book stock), record_transaction (receipt/issue/adjustment; rejects overflow past capacity, negative stock, or an adjustment with no reason), perform_reconciliation (computes expected closing stock, variance, and classification against configurable thresholds; resets the tank's book stock to the physical figure as the new baseline, audit-logged with old/new stock)
- [x] app/ui/tank_window.py: TankListWindow, TankFormDialog, TankDetailDialog (tabbed Transactions/Readings/Reconciliation with Receipt/Issue/Adjustment/Record Reading/Reconcile/Change Status actions); wired into MainWindow as a "Tanks" button and dashboard card, gated on INVENTORY_VIEW
- [x] tests/test_tank_service.py (26 tests, including parametrized variance-classification cases) and tests/test_tank_ui.py (7 tests)
- [x] Business rule confirmed by the user: every dispenser has exactly 2 nozzles, and each nozzle's fuel is commonly Petrol/Diesel/Power. `MAX_NOZZLES_PER_DISPENSER` now enforced in `NozzleService.create_nozzle`; `DEFAULT_FUEL_TYPES` (Petrol/Diesel/Power) now seeded automatically — see "Business Rules Confirmed By The User" below. 4 new tests (2 in test_nozzle_service.py, 2 in test_auth_rbac.py).
- [x] **Attendant self-service view** (requested by the user 2026-08-15): new `Permission.MY_ASSIGNMENT_VIEW`, granted only to `UserRole.ATTENDANT` (previously an empty permission set — attendants saw a completely blank dashboard). `ShiftService.get_my_active_assignment(actor_user_id)` looks up the acting user's own `Employee` record, then their currently active `NozzleAssignment` (via new `EmployeeRepository.get_by_user_id` and `NozzleAssignmentRepository.get_active_for_employee`). New `app/ui/my_shift_window.py` (`MyShiftWindow`) shows the assigned nozzle/fuel/dispenser/opening meter in a card, or an empty-state message if unassigned. "My Shift" button/dashboard card added to `MainWindow`, gated on `MY_ASSIGNMENT_VIEW`. 5 tests in `tests/test_shift_service.py`, 3 in `tests/test_my_shift_ui.py`.
- [x] **Fuel-sectioned reports** (requested by the user 2026-08-15: "a section for petrol, diesel and power"): new `app/services/report_service.py` — `ReportService.get_fuel_type_summary(actor_user_id)` (gated on `INVENTORY_VIEW`) aggregates, per fuel type, tank count/total capacity/total current stock, nozzle/active-nozzle counts, and the worst latest reconciliation variance. Returns a plain `FuelTypeSummary` dataclass per fuel type (not persisted — a computed view). New `app/ui/report_window.py` (`FuelTypeSummaryReportWindow`, one card per fuel type in a scroll area). "Reports" button/dashboard card added to `MainWindow`, gated on `INVENTORY_VIEW`. 4 tests in `tests/test_report_service.py`.
- [x] **User Management for all 6 roles** (requested by the user 2026-08-15: "create a login... for all the 6 roles and... multiple users [per role]"): new `app/services/user_service.py` — `UserService.create_user` (validates username/email uniqueness, role existence, enforces `validate_password_strength` — the first place this check was ever actually wired into the app despite existing since Phase 4), `list_users`, `set_user_active`/`unlock_user`/`change_user_role` (all require a non-blank reason, all audit-logged; accounts are deactivated/unlocked, never deleted). New `app/schemas/user.py` (`UserCreate`, username/email regex validation). New `app/ui/user_management_window.py` (`UserListWindow` table + `UserFormDialog` + `UserDetailDialog` for role change/activate-deactivate/unlock). "Users" button/dashboard card added to `MainWindow`, gated on `Permission.USER_MANAGE` — already granted only to ADMIN/OWNER via the existing `tuple(Permission)` grant, so this is enforced by the same role-based visibility pattern as every other module (no JWT needed; considered and rejected — see Architecture Decisions). Explored using JWT for auth (user question, 2026-08-15) and decided against it: this is a single-process desktop app with one DB, so the existing DB-backed session/token model already gives instant revocation (unlock/deactivate/logout take effect immediately) that JWT's stateless-by-design model would complicate for no benefit here. 16 tests in `tests/test_user_service.py`, 7 in `tests/test_user_management_ui.py`.

## Known Bugs (Fixed)
- [x] `app/services/inventory_service.py` defined a `PaymentRepository(Repository)` class with an unimported base class and SQLite-incompatible raw SQL (`NOW()`), which raised `NameError` on import. Removed, along with an unrelated unused `EmployeeService` stub. (fixed 2026-08-15)
- [x] `app/database/session.py` duplicated the `SessionLocal` factory already defined in `app/database/connection.py`. It now re-exports the single instance from `connection.py` instead of redefining it. (fixed 2026-08-15)
- [x] `app/models/role_permission.py` defined the `role_permissions` table but it was never imported anywhere, so the table silently never existed in the actual database. Now imported in `app/models/__init__.py` and wired as a real relationship. (fixed 2026-08-15)
- [x] `datetime.utcnow()` (deprecated in Python 3.12+, which this project targets 3.13+ for) replaced with `datetime.now(timezone.utc)` in `EntityMixin` and `inventory_service.py`. (fixed 2026-08-15)
- [x] SQLite foreign-key enforcement and WAL mode were never actually enabled despite being explicitly required by CLAUDE.md/problemstatement.md — fixed via a `connect` event listener in `app/database/connection.py`. (fixed 2026-08-15)
- [x] Every repository committed directly via `session.commit()` with no rollback on failure, meaning a single failed write would leave that login's shared session broken for every subsequent operation. Fixed via a shared `safe_commit()` helper used everywhere. (fixed 2026-08-15)
- [x] `ShiftService.open_shift` accepted a `supervisor_id` without checking it referenced a real user. (fixed 2026-08-15)
- [x] `app/database/connection.py`'s `get_connection()` was annotated/documented as a generator (`next(get_connection())`) but implemented as a plain `return`, which would raise `TypeError` if ever called as documented. It was also unused and encouraged bypassing the repository layer, so it was removed rather than fixed. (fixed 2026-08-15)
- [x] `app/main.py` had no error handling around `init_db()`/`seed_initial_data()` — any startup failure (disk full, permission denied, corrupted DB) crashed with a raw traceback. Now wrapped and translated into a single `DatabaseInitializationError`, logged via `app.core.logging.logger`. (fixed 2026-08-15)
- [x] Every UI dialog only caught `AppError`/`ValidationError`, so an unexpected exception (a DB error, a bug) from any service call would propagate uncaught through a Qt slot. Every dialog action across login/employee/attendance/shift now has a final `except Exception` that logs the full traceback and shows a generic, safe message via `describe_unexpected_error()` (`app/ui/qt_utils.py`) instead of crashing or silently misbehaving. (fixed 2026-08-15)
- [x] `get_database_path()` resolved the DB file relative to `app/database/connection.py`'s own location, which works in a normal checkout but would silently reset the database on every launch once packaged with PyInstaller (a onefile build re-extracts to a fresh temp directory every run). Fixed by detecting the frozen state and using a stable per-user directory (`%LOCALAPPDATA%\PetrolPumpERP`) instead. Found and fixed while setting up packaging, verified against a simulated fresh PC. (fixed 2026-08-15)

## Pending Modules
- **Shared UI base class for list-window/form-dialog boilerplate** — deliberately deferred (2026-08-16): 8 of the 9 `*_window.py` files repeat the same ~150-line table+add-button+dialog+error-label scaffold. Flagged in the 2026-08-16 build audit as a maintainability item; not attempted as part of resolving that audit's other 9 items since a refactor touching every UI file carries real regression risk and is better done as its own focused pass, not appended to an already large batch of changes.
- User-provisioning flow for employees who need login access (Employee.user_id can link an existing User; User Management now lets an admin create the login account itself, but there's no one-click "create login + link to this employee" combined flow yet — they're still two separate steps)
- Full HR/attendance/shift/nozzle/tank reports module (deferred to Phase 16: Reporting System) — the fuel-type-sectioned tank/nozzle summary (Petrol/Diesel/Power) is done (`ReportService.get_fuel_type_summary`) and now has PDF/Excel export + Print (`app/services/report_export.py`); still pending: attendance/shift/sales-style reports reusing that same export pattern.
- Holiday calendar / leave-balance tracking (Attendance can record LEAVE/HOLIDAY status per day, but there's no holiday calendar or leave-quota entity yet)
- Full shift-close reconciliation (cash/UPI/card/fuel) — deferred to Phase 15, once sales/payments modules exist; Phase 7 only covers opening meter/closing meter + nozzle assignment
- `Attendance.shift_label` is still free-text, not a real FK to `Shift` (both now exist; migrating this is still pending)
- Payments/credit modules (Phase 12-13; Phase 13's Credit Management is fully specified in ROADMAP.md per explicit user requirements 2026-08-16, not yet built — now unblocked since Phase 11 Sales is complete)
- Reconciliation module (full cash/UPI/card, not fuel — fuel reconciliation already exists, Phase 9)
- Printing for reports other than the fuel-type summary
- UI components beyond the MVP stub window

## Known Limitations
- No cloud deployment in the current phase (intentional - offline-only for now; see Future Scope)
- Single-file SQLite database
- Desktop-only deployment
- Permission matrix in `app/core/constants.py` (`ROLE_PERMISSIONS`) only covers the modules that exist so far (users, inventory, audit, employees, attendance, shifts, backups); it must grow as each new module (sales, etc.) is implemented
- `ADMIN` and `OWNER` currently carry byte-for-byte identical permissions (`tuple(Permission)` for both) — may be exactly right for a single-pump deployment, but was flagged in the 2026-08-16 audit as worth a deliberate decision rather than a default, since the two roles often diverge on financial visibility once a second location or investor exists
- No installer (Start Menu entry, uninstaller) yet — `dist/PetrolPumpERP.exe` is a raw standalone binary; fine for the team's first look, worth revisiting before a real multi-PC rollout
- SQLite's own on-disk storage for `Numeric` columns still round-trips through a float internally (a SQLite/SQLAlchemy driver limitation, not fixable from the app side) — the fix applied 2026-08-16 (`Numeric`/`Decimal` end-to-end in models, schemas, and Python-side arithmetic) still eliminates the actual risk that mattered: binary-float drift accumulating across chained business-logic arithmetic and inconsistent display rounding
- `Attendance.shift_label` is still a free-text field, not a foreign key to the now-existing `Shift` entity — should be migrated to a real relationship (a schema/migration change, deliberately not done as a drive-by edit)
- `EmployeeRepository.next_employee_code()` generates codes from a row count; fine for a single-user offline desktop app (rows are never hard-deleted) but would need a real sequence if this ever became multi-writer
- `Shift.get_by_date_and_label` + insert is a check-then-insert, not an atomic DB-level transaction; safe for a single-user offline desktop app but would need a real unique-constraint-driven retry under concurrent writers
- Service methods that pre-check existence/uniqueness (Employee, Attendance, Shift, NozzleAssignment) still rely on that check-then-insert pattern rather than catching the DB's `IntegrityError` and translating it — acceptable for a single-writer desktop app (now backed by real FK/unique enforcement as a safety net either way) but worth revisiting if the app ever gets concurrent writers

## Open Questions
- Number of attendants/fuel attendants needed?
- Required reports list beyond "broken down by fuel type" (which specific reports, over which date ranges, exported how)?
- Supplier management complexity?

## Business Rules Confirmed By The User
- (2026-08-15) A pump has a variable ("random") number of dispensers, but **every dispenser has exactly 2 nozzles**. Enforced in `NozzleService.create_nozzle` via `MAX_NOZZLES_PER_DISPENSER` (`app/core/constants.py`); a 3rd nozzle on the same dispenser raises `ConflictError`.
- (2026-08-15) Each nozzle dispenses exactly one fuel type, and that type is commonly **Petrol, Diesel, or Power** (a premium/branded fuel variant). These three are now seeded by default as `Fuel` rows (`DEFAULT_FUEL_TYPES` in constants.py, seeded via `_seed_fuel_types` in `app/database/seed.py`) so nozzle/tank setup has them available out of the box — seeded at `rate_per_liter=0.0` since real prices must be configured by the site, never guessed.
- (2026-08-16) Credit customers ("crediters") need full lifecycle tracking — who they are, whether they've paid, and their activity broken down by fuel type (Petrol/Diesel/Power) in reports, reusing the fuel-type-summary reporting pattern already established for tanks/nozzles. Reserved as Phase 13 (Credit Management), fleshed out in ROADMAP.md with the full checklist — Sales (Phase 11) is now complete, so this is unblocked and ready to build next.

## Assumptions
- Single petrol pump location
- Single computer deployment
- Offline-only operation for the current phase
- Single location (single pump)
- No cloud integration in the current phase (see Future Scope)

## Architecture Decisions
- Desktop-only, offline-only for the current phase (no web, no cloud) — see Future Scope for the planned second phase
- SQLite single-file database
- PySide6 for UI
- SQLAlchemy 2.x ORM
- Clean architecture with layers: Presentation → Application → Domain → Repository → Database
- Business logic separated from UI
- RBAC for access control
- Service layer for business rules

## Security Decisions
- Password hashing with PBKDF2-HMAC-SHA256 (200,000 iterations) + per-password random salt (`app/core/security.py`)
- RBAC role-based access control
- Audit logging for all changes, now actually viewable via the Audit Log screen (`Permission.AUDIT_VIEW`, previously defined but unused)
- Session management with auto logout
- Forced password rotation after any admin-set password (new account or reset) — `User.must_change_password`
- No internet dependency

## Testing Status
- [x] Core setup smoke tests (`tests/test_core_setup.py`) — 5/5 passing (init/seed success path, startup DB failures raise a clean `DatabaseInitializationError`, frozen-build DB path resolves to `%LOCALAPPDATA%` not the temp extraction dir, env-var override still wins even when frozen)
- [x] Authentication/RBAC tests (`tests/test_auth_rbac.py`) — 15/15 passing (login success/failure, generic error messages, lockout, permission checks, session validate/expire/logout, password policy, audit logging, decorator enforcement, default fuel-type seeding and its idempotency)
- [x] Login UI tests (`tests/test_login_ui.py`) — 7/7 passing (login screen display, validation, success/failure paths, logout, auto-logout on expiry, unexpected-error fallback)
- [x] Employee/HR tests (`tests/test_employee_service.py`) — 16/16 passing (creation, validation, permissions, status/exit workflow, documents, audit logging)
- [x] Employee/HR UI tests (`tests/test_employee_ui.py`) — 10/10 passing (list/search, permission-based visibility, form validation, edit, status/exit, documents, unexpected-error fallback)
- [x] Attendance tests (`tests/test_attendance_service.py`) — 13/13 passing (marking, duplicate rejection, permissions, schema validation, correction workflow, filtering)
- [x] Attendance UI tests (`tests/test_attendance_ui.py`) — 8/8 passing (visibility, date filtering, marking, duplicate rejection, correction reason requirement, view-only disabling, unexpected-error fallback)
- [x] Shift/nozzle-assignment tests (`tests/test_shift_service.py`) — 23/23 passing (open/close, duplicate rejection, nozzle-assignment prevention rules, meter validation, reopen workflow and permission, RBAC)
- [x] Shift UI tests (`tests/test_shift_ui.py`) — 7/7 passing (visibility, list display, open/assign/close/reopen flows, unexpected-error fallback)
- [x] Database integrity tests (`tests/test_database_integrity.py`) — 5/5 passing (WAL mode active, FK enforcement active, invalid FK rejected, session recovers after `safe_commit` rollback, documents the broken behavior without it)
- [x] Nozzle Management tests (`tests/test_nozzle_service.py`) — 18/18 passing (create dispenser/nozzle, duplicate-code rejection, status-change reason requirement, blocks deactivating a nozzle with an active assignment, the confirmed 2-nozzles-per-dispenser cap, RBAC)
- [x] Nozzle Management UI tests (`tests/test_nozzle_ui.py`) — 8/8 passing (visibility, form validation, tab display, permission gating)
- [x] Tank & Inventory tests (`tests/test_tank_service.py`) — 26/26 passing (tank creation, capacity/negative-stock guards, receipt/issue/adjustment rules, reading vs. book-stock separation, parametrized variance classification, reconciliation math including period rollover, RBAC)
- [x] Tank & Inventory UI tests (`tests/test_tank_ui.py`) — 7/7 passing (visibility, form validation, transaction/reconciliation flows, unexpected-error fallback)
- [x] Attendant self-service tests (`tests/test_shift_service.py` additions) — 5/5 passing (`get_my_active_assignment` lookup, no-employee-record case, permission enforcement); UI (`tests/test_my_shift_ui.py`) — 3/3 passing
- [x] Fuel-sectioned report tests (`tests/test_report_service.py`) — 4/4 passing (per-fuel-type aggregation, variance rollup, permission enforcement)
- [x] User Management tests (`tests/test_user_service.py`) — 16/16 passing (create/duplicate/weak-password/unknown-role/permission-denied, activate/deactivate, unlock, role-change, multiple users per role, audit logging); UI (`tests/test_user_management_ui.py`) — 7/7 passing (visibility, form validation, duplicate rejection, activate/deactivate/unlock reflected in the detail dialog)
- [x] Password self-service tests — 9 new in `test_user_service.py` (reset_password, change_own_password, RBAC on each) + 7 in `tests/test_change_password_ui.py` (dialog accept/reject paths, forced dialog can't be closed, full `AppController` forced-rotation-then-MainWindow flow)
- [x] Backup/restore tests — `tests/test_backup_restore.py` (7, including the WAL-file-capture case that's the whole reason the online backup API is used instead of a raw file copy) + `tests/test_backup_service.py` (10, RBAC/audit/the pre-restore safety backup) + `tests/test_backup_ui.py` (3)
- [x] Audit log viewer tests — `tests/test_audit_service.py` (8, search filters, RBAC) + `tests/test_audit_log_ui.py` (4)
- [x] Report export tests — `tests/test_report_export.py` (5, PDF text content verified via `pypdf`, Excel structure via `openpyxl`) + `tests/test_report_ui.py` (4, export button wiring with `QFileDialog` mocked)
- [x] Two new deterministic regression tests in `test_tank_service.py` pinning the local/UTC day-boundary reconciliation bug (see Known Bugs Fixed)
- [x] `test_core_setup.py` gained 2 tests for the new file-logging behavior, including the one that caught the Alembic `disable_existing_loggers` bug
- [x] Phase 11 Sales tests — `tests/test_sale_service.py` (16, snapshot pricing, tank-resolution fallback/ambiguity, cancellation compensating adjustment, RBAC) + `tests/test_sales_ui.py` (5, full picker vs. self-service dual-path UI) + new permission-layering regression tests in `test_tank_service.py`
- [x] Dashboard KPI strip tests — `tests/test_dashboard_service.py` (7: per-role permission gating, today's-sales counting excludes cancelled sales, open-shift count, low-stock tank flagging, pending purchase order count)
- [ ] Integration tests (pending)
- [ ] The shared UI base-class refactor's own tests (n/a — refactor itself deferred, see Pending Modules)

**348/348 tests passing project-wide** (up from 202 at the start of the 2026-08-16 audit-resolution session; 265 after the audit, 303 after Phase 10 Procurement, 329 after Phase 11 Sales, 336 after the dashboard KPI strip, 348 after Phase 12 Payments).

## Backup Status
- [x] Automatic pre-migration backups (`app/database/backup.py` + `init_db()`) and on-demand manual backups via the Backups screen — both use SQLite's online backup API, not a raw file copy, so a backup taken while WAL mode has uncommitted-to-disk data is still transactionally consistent
- [x] Restore tested — `BackupService.restore_backup` takes its own safety backup first, requires a reason, and is audit-logged; `tests/test_backup_restore.py`/`test_backup_service.py` cover the overwrite-the-live-file path directly

## Deployment Status
- [x] PyInstaller packaging — `petrol_pump_erp.spec` + `requirements-build.txt`; `pyinstaller petrol_pump_erp.spec` produces a single `dist/PetrolPumpERP.exe`, verified end-to-end against a simulated fresh PC (empty fake `%LOCALAPPDATA%`): correct database created in the right per-user location, login window rendered correctly. The spec now also bundles `alembic.ini`/`alembic/` as data files so the frozen build can run real migrations. No proper installer (Start Menu entry/uninstaller) yet — just a standalone .exe, which is what the user asked for ("downloadable so I can install this app... works there freshly on their different PCs").
- [x] Initial commit created and pushed to GitHub
- [x] CI: `.github/workflows/tests.yml` runs the full suite on every push/PR (`windows-latest`)

## Git/GitHub Status
- Repository: https://github.com/Rahil-Mokashi/initial-capstone.git
- Active branch: `feature/core-framework` (not yet merged to `main`)
- Latest work: Phase 11 Sales Management (Sale/Customer models, snapshot pricing, cancellation with compensating tank adjustments, dual-path full-picker/self-service UI), on top of the full build audit resolution (2026-08-16) — Alembic, Decimal-safe money/volume columns, password self-service, production logging, backup/restore, an audit log viewer, PDF/Excel report export, a user-reported Enter-key navigation fix, and a dashboard layout bug — and Phase 10 Procurement Management, Phase 9 Tank & Inventory Management, the standalone .exe packaging, and the eye-catching/minimal UI redesign
- Commit messages in this project do not carry a `Co-Authored-By: Claude` trailer, per explicit user preference (2026-08-16) — GitHub parses that trailer to add a second contributor to the repo's Contributors list, which the user does not want. Two already-pushed commits that had it were fixed via `git filter-branch --msg-filter` (message-only, file contents byte-identical) and a confirmed `--force-with-lease` push.

## Future Scope
- The current offline desktop application is Phase 1 of a two-phase plan. Once the offline ERP proves itself in real use, the plan is to build a second phase: a web application backed by a cloud database with cloud data synchronization. Architecture decisions in the current phase (repository/service separation, UUID primary keys, clean domain models) are being made with this eventual migration in mind, even though no cloud/web code is being written yet.

## UI/UX Decisions
- The client expects a clean, elegant, polished UI (not a bare functional stub) for every screen, balanced against the problem statement's UX priorities (speed, minimal clicks, large readable numbers for a busy pump environment). `app/ui/styles.py` holds one shared stylesheet so every future screen stays visually consistent — extend it rather than styling widgets ad hoc.
- Explicit direction (2026-08-15): make the UI "eye catching and minimal at the same time." Palette refreshed to one confident indigo primary (`#4F46E5`) with a single sparingly-used amber accent, rather than adding more colors. Applied concretely via: a split-panel login screen (gradient brand hero on the left with a badge/tagline/feature bullets, the form card on the right) instead of a bare centered form, and a real landing dashboard on `MainWindow` (personalized greeting, today's date, clickable icon-badge quick-access cards to Employees/Attendance/Shifts) instead of a static "Welcome" label. Both keep the same restrained, whitespace-driven language as the rest of the app — eye-catching comes from hierarchy and one strong color, not decoration.
- Known Qt/QSS gotcha worth remembering for future custom widgets: a plain `QWidget` subclass needs `self.setAttribute(Qt.WA_StyledBackground, True)` or its stylesheet `background-color`/`border`/`border-radius` will silently not render (see `DashboardCard` in `app/ui/main_window.py`). Built-in widgets like `QFrame`/`QPushButton`/`QDialog` don't need this.

## Next Task
Phases 4-12 are complete end-to-end: Auth/RBAC, Employee/HR, Attendance, Shift, Nozzle, Tank & Inventory, Procurement, Sales, Payments, plus the attendant self-service view, fuel-sectioned reports, User Management, and the 2026-08-16 build-audit resolution pass (Alembic, Decimal-safe money columns, password self-service, production logging, backup/restore, an audit log viewer, PDF/Excel report export). The dashboard was redesigned per explicit user feedback (grouped sections, decluttered top bar) and then enhanced further with a live KPI strip (today's sales, open shifts, low-stock tanks, pending purchase orders — see Dashboard redesign above). 348/348 tests passing. The one deferred item is the shared UI base-class refactor (Pending Modules). Per the user's standing instruction to keep building autonomously without further check-ins: continue to Phase 13 (Credit Management, now unblocked since Sales and Payments both exist) and beyond, and keep analyzing the app for further improvements as each phase lands (including where offline-capable ML/analytics genuinely add value, per explicit user request).
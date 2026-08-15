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
Phase 7: Shift Management is done end-to-end (service layer + UI, tested), including nozzle assignment. Phases 4-6 (Auth & RBAC, Employee & HR, Attendance) are also done end-to-end. Database integrity (FK enforcement, WAL mode, safe commit/rollback) was audited and hardened across the whole app.

## Known Bugs (Fixed)
- [x] `app/services/inventory_service.py` defined a `PaymentRepository(Repository)` class with an unimported base class and SQLite-incompatible raw SQL (`NOW()`), which raised `NameError` on import. Removed, along with an unrelated unused `EmployeeService` stub. (fixed 2026-08-15)
- [x] `app/database/session.py` duplicated the `SessionLocal` factory already defined in `app/database/connection.py`. It now re-exports the single instance from `connection.py` instead of redefining it. (fixed 2026-08-15)
- [x] `app/models/role_permission.py` defined the `role_permissions` table but it was never imported anywhere, so the table silently never existed in the actual database. Now imported in `app/models/__init__.py` and wired as a real relationship. (fixed 2026-08-15)
- [x] `datetime.utcnow()` (deprecated in Python 3.12+, which this project targets 3.13+ for) replaced with `datetime.now(timezone.utc)` in `EntityMixin` and `inventory_service.py`. (fixed 2026-08-15)
- [x] SQLite foreign-key enforcement and WAL mode were never actually enabled despite being explicitly required by CLAUDE.md/problemstatement.md — fixed via a `connect` event listener in `app/database/connection.py`. (fixed 2026-08-15)
- [x] Every repository committed directly via `session.commit()` with no rollback on failure, meaning a single failed write would leave that login's shared session broken for every subsequent operation. Fixed via a shared `safe_commit()` helper used everywhere. (fixed 2026-08-15)
- [x] `ShiftService.open_shift` accepted a `supervisor_id` without checking it referenced a real user. (fixed 2026-08-15)

## Pending Modules
- User-provisioning flow for employees who need login access (currently Employee.user_id can only link an *existing* User; there's no "create login for this employee" service method yet)
- HR/attendance/shift reports module (deferred to Phase 16: Reporting System)
- Holiday calendar / leave-balance tracking (Attendance can record LEAVE/HOLIDAY status per day, but there's no holiday calendar or leave-quota entity yet)
- Full Nozzle/Dispenser master-data management (CRUD, status transitions, UI) — Phase 8; only the minimal models needed for shift assignment exist so far
- Full shift-close reconciliation (cash/UPI/card/fuel) — deferred to Phase 15, once sales/payments/inventory modules exist; Phase 7 only covers opening meter/closing meter + nozzle assignment
- Tank/inventory modules beyond the current Fuel stub
- Sales, payments, credit modules
- Reconciliation module
- Reporting and printing modules
- Backup/restore module
- UI components beyond the MVP stub window
- Packaging and deployment

## Known Limitations
- No cloud deployment in the current phase (intentional - offline-only for now; see Future Scope)
- Single-file SQLite database
- Desktop-only deployment
- `Fuel` model uses `Float` for rate/capacity/stock fields rather than `Numeric`/fixed-point — acceptable for the MVP stub but should be revisited before real financial data is stored, per the project's data-integrity priority
- Default seeded admin password (`Admin@123`, in `app/database/seed.py`) is a known dev-only credential; must be changed before any real deployment. No "force password change on first login" flow exists yet.
- Permission matrix in `app/core/constants.py` (`ROLE_PERMISSIONS`) only covers the modules that exist so far (users, inventory, audit, employees, attendance, shifts); it must grow as each new module (sales, etc.) is implemented
- `Attendance.shift_label` is still a free-text field, not a foreign key to the now-existing `Shift` entity — should be migrated to a real relationship (a schema/migration change, deliberately not done as a drive-by edit)
- `EmployeeRepository.next_employee_code()` generates codes from a row count; fine for a single-user offline desktop app (rows are never hard-deleted) but would need a real sequence if this ever became multi-writer
- `Shift.get_by_date_and_label` + insert is a check-then-insert, not an atomic DB-level transaction; safe for a single-user offline desktop app but would need a real unique-constraint-driven retry under concurrent writers
- Service methods that pre-check existence/uniqueness (Employee, Attendance, Shift, NozzleAssignment) still rely on that check-then-insert pattern rather than catching the DB's `IntegrityError` and translating it — acceptable for a single-writer desktop app (now backed by real FK/unique enforcement as a safety net either way) but worth revisiting if the app ever gets concurrent writers

## Open Questions
- Number of attendants/fuel attendants needed?
- Number of dispensers/nozzles required?
- Required reports list?
- Supplier management complexity?

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
- Audit logging for all changes
- Session management with auto logout
- No internet dependency

## Testing Status
- [x] Core setup smoke tests (`tests/test_core_setup.py`) — 2/2 passing
- [x] Authentication/RBAC tests (`tests/test_auth_rbac.py`) — 13/13 passing (login success/failure, generic error messages, lockout, permission checks, session validate/expire/logout, password policy, audit logging, decorator enforcement)
- [x] Login UI tests (`tests/test_login_ui.py`) — 6/6 passing (login screen display, validation, success/failure paths, logout, auto-logout on expiry)
- [x] Employee/HR tests (`tests/test_employee_service.py`) — 16/16 passing (creation, validation, permissions, status/exit workflow, documents, audit logging)
- [x] Employee/HR UI tests (`tests/test_employee_ui.py`) — 9/9 passing (list/search, permission-based visibility, form validation, edit, status/exit, documents)
- [x] Attendance tests (`tests/test_attendance_service.py`) — 13/13 passing (marking, duplicate rejection, permissions, schema validation, correction workflow, filtering)
- [x] Attendance UI tests (`tests/test_attendance_ui.py`) — 7/7 passing (visibility, date filtering, marking, duplicate rejection, correction reason requirement, view-only disabling)
- [x] Shift/nozzle-assignment tests (`tests/test_shift_service.py`) — 23/23 passing (open/close, duplicate rejection, nozzle-assignment prevention rules, meter validation, reopen workflow and permission, RBAC)
- [x] Shift UI tests (`tests/test_shift_ui.py`) — 6/6 passing (visibility, list display, open/assign/close/reopen flows)
- [x] Database integrity tests (`tests/test_database_integrity.py`) — 5/5 passing (WAL mode active, FK enforcement active, invalid FK rejected, session recovers after `safe_commit` rollback, documents the broken behavior without it)
- [ ] Integration tests (pending)
- [ ] Report generation tests (pending)
- [ ] Backup/Restore tests (pending)

## Backup Status
- [ ] Initial backup created (pending)

## Deployment Status
- [ ] PyInstaller packaging (pending)
- [x] Initial commit created and pushed to GitHub

## Git/GitHub Status
- Repository: https://github.com/Rahil-Mokashi/initial-capstone.git
- Active branch: `feature/core-framework` (not yet merged to `main`)
- Latest work: Phase 7 Shift Management (shift open/close, nozzle assignment, reopen workflow) plus a database-integrity hardening pass (FK enforcement, WAL mode, safe commit/rollback)

## Future Scope
- The current offline desktop application is Phase 1 of a two-phase plan. Once the offline ERP proves itself in real use, the plan is to build a second phase: a web application backed by a cloud database with cloud data synchronization. Architecture decisions in the current phase (repository/service separation, UUID primary keys, clean domain models) are being made with this eventual migration in mind, even though no cloud/web code is being written yet.

## UI/UX Decisions
- The client expects a clean, elegant, polished UI (not a bare functional stub) for every screen, balanced against the problem statement's UX priorities (speed, minimal clicks, large readable numbers for a busy pump environment). `app/ui/styles.py` holds one shared stylesheet so every future screen stays visually consistent — extend it rather than styling widgets ad hoc.

## Next Task
Phase 7 (Shift Management) is complete end-to-end, service layer and UI (99/99 tests passing project-wide), and the database foundation has been hardened (FK enforcement, WAL mode, safe commit/rollback). Next: either migrate `Attendance.shift_label` to a real FK against `Shift`, or move on to Phase 8 (Nozzle Management — full CRUD/UI for Dispenser/Nozzle master data) per ROADMAP.md.
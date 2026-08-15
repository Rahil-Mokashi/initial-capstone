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
- Foreign key constraints
- WAL mode enabled
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

## Current Module
Phase 4: Authentication & RBAC (in progress) — building on the completed core framework.

## Known Bugs (Fixed)
- [x] `app/services/inventory_service.py` defined a `PaymentRepository(Repository)` class with an unimported base class and SQLite-incompatible raw SQL (`NOW()`), which raised `NameError` on import. Removed, along with an unrelated unused `EmployeeService` stub. (fixed 2026-08-15)
- [x] `app/database/session.py` duplicated the `SessionLocal` factory already defined in `app/database/connection.py`. It now re-exports the single instance from `connection.py` instead of redefining it. (fixed 2026-08-15)
- [x] `app/models/role_permission.py` defined the `role_permissions` table but it was never imported anywhere, so the table silently never existed in the actual database. Now imported in `app/models/__init__.py` and wired as a real relationship. (fixed 2026-08-15)
- [x] `datetime.utcnow()` (deprecated in Python 3.12+, which this project targets 3.13+ for) replaced with `datetime.now(timezone.utc)` in `EntityMixin` and `inventory_service.py`. (fixed 2026-08-15)

## Pending Modules
- Employee/HR module
- Attendance module
- Shift management
- Nozzle/tank/inventory modules beyond the current Fuel stub
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
- Permission matrix in `app/core/constants.py` (`ROLE_PERMISSIONS`) only covers the modules that exist so far (users, inventory, audit); it must grow as each new module (sales, shifts, HR, etc.) is implemented

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
- Latest work: Phase 4 Authentication & RBAC implementation (auth service, sessions, audit log, permission decorator, seeding, tests)

## Future Scope
- The current offline desktop application is Phase 1 of a two-phase plan. Once the offline ERP proves itself in real use, the plan is to build a second phase: a web application backed by a cloud database with cloud data synchronization. Architecture decisions in the current phase (repository/service separation, UUID primary keys, clean domain models) are being made with this eventual migration in mind, even though no cloud/web code is being written yet.

## Next Task
Phase 4 core pieces (login, sessions, RBAC, audit logging, tests) are implemented. Remaining Phase 4 items: wire an actual login UI flow (currently only the MVP stub window exists) and expand the permission matrix as new modules are added. After that, move to Phase 5 (Employee & HR Management) per ROADMAP.md.
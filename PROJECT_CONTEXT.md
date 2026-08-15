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

## Current Module
Phase 4: Authentication & RBAC (in progress) — building on the completed core framework.

## Known Bugs (Fixed)
- [x] `app/services/inventory_service.py` defined a `PaymentRepository(Repository)` class with an unimported base class and SQLite-incompatible raw SQL (`NOW()`), which raised `NameError` on import. Removed, along with an unrelated unused `EmployeeService` stub. (fixed 2026-08-15)
- [x] `app/database/session.py` duplicated the `SessionLocal` factory already defined in `app/database/connection.py`. It now re-exports the single instance from `connection.py` instead of redefining it. (fixed 2026-08-15)

## Pending Modules
- RBAC: wire `role_permissions` many-to-many relationship, seed roles/permissions, implement real permission checks (in progress)
- Session management with auto logout (in progress)
- Audit logging for authentication events (in progress)
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
- RBAC permission checking (`AuthService.check_permission`) is currently a stub that always returns `False`; being implemented now in Phase 4

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
- [ ] Authentication/RBAC tests (in progress, Phase 4)
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
- Latest pushed commit: cleanup fix for `inventory_service.py`/`session.py`

## Future Scope
- The current offline desktop application is Phase 1 of a two-phase plan. Once the offline ERP proves itself in real use, the plan is to build a second phase: a web application backed by a cloud database with cloud data synchronization. Architecture decisions in the current phase (repository/service separation, UUID primary keys, clean domain models) are being made with this eventual migration in mind, even though no cloud/web code is being written yet.

## Next Task
Implement Phase 4 (Authentication & RBAC): audit logging, session management, role/permission seeding and enforcement, and tests.
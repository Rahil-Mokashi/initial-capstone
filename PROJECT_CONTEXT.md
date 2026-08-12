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
- [x] User model (app/models/user.py)
- [x] Role model (app/models/role.py)
- [x] Permission model (app/models/permission.py)
- [x] RolePermission model (app/models/role_permission.py)
- [x] Inventory Service (app/services/inventory_service.py)
- [x] Auth Service (app/services/auth_service.py)

## Current Module
Service layer development - building business logic services

## Pending Modules
- Complete model definitions for all entities
- Repository layer
- Additional service layers (employee, shift, sales, payments, etc.)
- UI components
- Testing framework
- Documentation
- Packaging and deployment

## Known Limitations
- No cloud deployment (intentional - offline-only)
- Single-file SQLite database
- Desktop-only deployment
- Models directory contains placeholder content

## Open Questions
- Number of attendants/fuel attendants needed?
- Number of dispensers/nozzles required?
- Required reports list?
- Supplier management complexity?

## Assumptions
- Single petrol pump location
- Single computer deployment
- Offline-only operation
- Single location (single pump)
- No cloud integration (intentional)

## Architecture Decisions
- Desktop-only (no web, no cloud)
- SQLite single-file database
- PySide6 for UI
- SQLAlchemy 2.x ORM
- Clean architecture with layers: Presentation → Application → Domain → Repository → Database
- Business logic separated from UI
- RBAC for access control
- Service layer for business rules

## Security Decisions
- Password hashing with werkzeug/security
- RBAC role-based access control
- Audit logging for all changes
- Session management with auto logout
- No internet dependency

## Testing Status
- [ ] Unit tests (pending)
- [ ] Integration tests (pending)
- [ ] Report generation tests (pending)
- [ ] Backup/Restore tests (pending)

## Backup Status
- [ ] Initial backup created (pending)

## Deployment Status
- [ ] PyInstaller packaging (pending)
- [ ] Initial commit created (in progress)

## Git/GitHub Status
- Repository initializing
- Initial commit in progress

## Next Task
Set up Git repository and push initial files to GitHub
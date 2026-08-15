# Petrol Pump ERP - Development Roadmap

## Phase 1: Project Initialization & Discovery (Completed)
- [x] Create PROJECT_CONTEXT.md
- [x] Create CLAUDE.md
- [x] Create README.md
- [x] Create ARCHITECTURE.md
- [x] Create initial folder structure
- [x] Initialize Git repository
- [x] Create initial commit
- [x] Create .gitignore

## Phase 2: Architecture Documentation (Completed)
- [x] Create system architecture documentation
- [x] Create Mermaid diagrams
- [x] Create database ER diagram
- [x] Create business workflow diagrams
- [x] Create RBAC matrix
- [x] Create technical specifications

## Phase 3: Database Design & Core Framework (Completed ✅)
- [x] Design core database schema
- [x] Create SQLAlchemy models
- [x] Set up database connection module
- [x] Define UUID primary key strategy
- [x] Define foreign key relationships
- [x] Create indexes for performance
- [x] Enable WAL mode (marked done here originally, but the `PRAGMA` was never actually wired up until 2026-08-15 — see Phase 7's database-integrity note)
- [x] Enable foreign key constraints (same correction — actually enforced as of 2026-08-15)
- [x] Test database connection
- [x] Create core models (User, Role, Permission, Fuel)
- [x] Create repositories (User, Fuel)
- [x] Create services (Auth, Inventory)
- [x] Implement password hashing
- [x] Create initial data seed (admin user)
- [x] MVP UI stub with PySide6 support
- [x] Core tests passing

## Phase 4: Authentication & RBAC (Complete)
- [x] Create user management
- [x] Implement password hashing
- [x] Create login/logout functionality (AuthService.authenticate/logout — service layer only, no UI yet)
- [x] Implement session management (UserSession model, session token hashing, expiry, auto logout on validate_session)
- [x] Create role-based access control (role_permissions relationship, ROLE_PERMISSIONS matrix, AuthService.check_permission)
- [x] Define user roles: ADMIN, OWNER, MANAGER, ACCOUNTANT, SHIFT_SUPERVISOR, ATTENDANT (app/core/constants.py UserRole enum, seeded)
- [x] Implement permission checking decorators (require_permission in app/core/permissions.py)
- [x] Create audit logging for authentication events (AuditLog model + AuditLogRepository; login success/failure/lockout/logout/session expiry all recorded)
- [x] Implement password policy (validate_password_strength — min length, upper/lower/digit)
- [x] Add login attempt protection (failed_attempts/is_locked fields on User; lockout logic in AuthService)
- [x] Login UI screen (app/ui/login_window.py — styled card, wired to AuthService, error handling)
- [x] Main window shows current user/role and supports logout + auto-logout on session expiry
- [ ] Wire permission decorator into real service methods as those services are built

## Phase 5: Employee & HR Management (Complete except HR reports, deferred to Phase 16)
- [x] Create employee master data (Employee model, EmployeeService.create_employee/update_employee)
- [x] Implement employee documents (EmployeeDocument model, add_document/remove_document, soft delete)
- [x] Track joining/exit information (joining_date/exit_date, record_exit — never hard-deletes the employee)
- [x] Create department management (department field on Employee — free-text for now, no separate Department entity yet)
- [x] Implement employee status tracking (EmployeeStatus enum: active/on_leave/suspended/terminated, change_status)
- [x] Create emergency contact tracking (emergency_contact_name/phone fields)
- [x] Assign employees to outlets/departments (assigned_outlet field, defaults to "Main Outlet" per single-location assumption)
- [ ] Create HR reports module (deferred to Phase 16: Reporting System)
- [x] Employee/HR UI screens (app/ui/employee_window.py: list with search, add form, detail/edit dialog with status/exit workflow and document management)
- [ ] User-provisioning flow for employees who need login access (Employee.user_id can currently only link an existing User)

## Phase 6: Attendance Management (Complete except reports/holiday calendar)
- [x] Track check-in/check-out (Attendance.check_in_time/check_out_time, validated check-out >= check-in)
- [x] Manage attendance status (present, absent, late, half day, leave, holiday — AttendanceStatus enum)
- [x] Record shift and supervisor information (shift_label free-text pending Phase 7's Shift entity; supervisor_id FK to User)
- [x] Implement attendance correction workflow (AttendanceService.correct_attendance: requires a reason, permission-checked, audit-logged with old/new snapshot, never a silent overwrite)
- [ ] Create attendance reports (deferred to Phase 16: Reporting System)
- [x] Track overtime-ready fields (overtime_minutes, non-negative validated)
- [ ] Implement holiday tracking (HOLIDAY is a valid status per day, but there's no holiday calendar entity yet)
- [x] Attendance UI (app/ui/attendance_window.py: date-filterable roster, mark dialog, correction dialog)

## Phase 7: Shift Management (Complete except full reconciliation, deferred to Phase 15)
- [x] Implement shift opening workflow (ShiftService.open_shift — one row per shift_date+shift_label, duplicate rejected)
- [x] Record opening meter readings (NozzleAssignmentCreate.opening_meter, non-negative validated)
- [x] Assign attendants to nozzles per shift (assign_nozzle — rejects a second active assignment for the same employee or the same nozzle within a shift, rejects assignment to an inactive nozzle or a non-open shift)
- [x] Track shift start/end times (Shift.start_time/end_time)
- [ ] Implement shift closing with reconciliation (closing meter readings are captured via complete_nozzle_assignment and required before close_shift will succeed; cash/UPI/card/fuel reconciliation itself is deferred to Phase 15, once sales/payments/inventory exist)
- [x] Prevent editing of finalized shifts (assign/complete/cancel all rejected once a shift is closed)
- [x] Create controlled reopening/adjustment workflows (reopen_shift: requires the stricter SHIFT_REOPEN permission — not granted to SHIFT_SUPERVISOR — plus a non-blank reason, audit-logged)
- [ ] Create shift reports (deferred to Phase 16: Reporting System)
- [x] Shift UI (app/ui/shift_window.py: list, open dialog, detail dialog with assign/complete/cancel/close/reopen)

## Phase 8: Nozzle Management (Complete except reports, deferred to Phase 16)
- [x] Create nozzle master data (NozzleService.create_dispenser/create_nozzle, full CRUD via app/ui/nozzle_window.py)
- [x] Track fuel types per nozzle (Nozzle.fuel_id FK to the existing Fuel model)
- [x] Implement nozzle status (active, inactive, maintenance — NozzleStatus enum; only "active" nozzles can be assigned; set_nozzle_status requires a reason and is audit-logged)
- [x] Create nozzle assignment history (NozzleAssignment rows persist per shift; no dedicated history/report view yet)
- [x] Track opening/closing meter readings (NozzleAssignment.opening_meter/closing_meter, closing validated >= opening)
- [x] Prevent duplicate nozzle assignments (enforced in ShiftService.assign_nozzle — see Phase 7)
- [ ] Create nozzle reports (deferred to Phase 16)
- [x] Full Dispenser/Nozzle master-data UI (app/ui/nozzle_window.py: tabbed Dispensers/Nozzles, add forms, status-change with reason; deactivating a nozzle currently assigned in an open shift is blocked)

## Phase 9: Tank & Inventory Management
- [ ] Create tank master data
- [ ] Track fuel types and capacity
- [ ] Record tank dimensions and calibration
- [ ] Implement dip reading tracking
- [ ] Track current stock levels
- [ ] Record tank transactions (receipts, issues, adjustments)
- [ ] Implement fuel reconciliation
- [ ] Create tank inventory reports

## Phase 10: Procurement Management
- [ ] Create supplier master data
- [ ] Implement purchase order creation
- [ ] Track fuel delivery process
- [ ] Implement delivery verification
- [ ] Create fuel quality verification tracking
- [ ] Record pre-dip and post-dip readings
- [ ] Update inventory on delivery
- [ ] Create supplier invoice management
- [ ] Implement supplier payment tracking
- [ ] Create procurement reports

## Phase 11: Sales Management
- [ ] Create sale recording functionality
- [ ] Track sale details (date, time, shift, attendant, nozzle, fuel type)
- [ ] Record quantity, rate, and amount
- [ ] Support multiple payment methods (cash, UPI, card, credit)
- [ ] Prevent duplicate sales
- [ ] Implement sale cancellation/reversal workflow
- [ ] Track customer information where applicable
- [ ] Generate sales receipts
- [ ] Create sales reports

## Phase 12: Payment Management
- [ ] Track cash payments separately
- [ ] Track UPI payments with reference numbers
- [ ] Track card payments with authorization codes
- [ ] Track credit sales separately
- [ ] Implement payment status tracking (success, pending, failed, reversed, refunded)
- [ ] Create payment reconciliation workflows
- [ ] Track payment responsibility by attendant
- [ ] Create payment reports

## Phase 13: Credit Management
- [ ] Create customer master data
- [ ] Implement credit account management
- [ ] Set credit limits
- [ ] Track credit sales and invoices
- [ ] Record customer payments
- [ ] Calculate outstanding balances
- [ ] Implement credit blocking when limit exceeded
- [ ] Generate customer statements
- [ ] Track overdue amounts
- [ ] Create credit reports

## Phase 14: Expense Management
- [ ] Create expense category management
- [ ] Track expense details (amount, date, employee, shift)
- [ ] Record payment method for expenses
- [ ] Track expense receipts
- [ ] Implement expense approval workflow
- [ ] Support expense reports
- [ ] Create expense reconciliation
- [ ] Generate expense reports

## Phase 15: Reconciliation Management
- [ ] Implement cash reconciliation workflow
- [ ] Implement UPI reconciliation workflow
- [ ] Implement card reconciliation workflow
- [ ] Implement fuel reconciliation workflow
- [ ] Implement expense reconciliation workflow
- [ ] Implement shift reconciliation workflow
- [ ] Create discrepancy detection workflow
- [ ] Create exception handling for variances
- [ ] Create supervisor/manager review workflow
- [ ] Create reconciliation reports

## Phase 16: Reporting System
- [ ] Implement daily reports (sales, fuel, payment, cash, UPI, card, credit, expense, inventory, reconciliation, attendant, shift, tank, nozzle, purchase)
- [ ] Implement shift reports (summary, attendant-wise, nozzle-wise, fuel-wise, payment-wise, reconciliation)
- [ ] Implement attendant reports (attendance, shift history, nozzle assignment, sales, fuel volume, transaction counts, collections, reconciliation history)
- [ ] Implement HR reports (employee master, attendance, late arrival, absence, leave, shift attendance, performance, nozzle assignment)
- [ ] Implement inventory reports (tank stock, fuel movement, opening/closing stock, fuel purchase/sales, tank variance, low stock)
- [ ] Implement financial reports (cash book, payment summary, expense summary, customer outstanding, credit sales, customer ledger, supplier ledger, purchase summary, financial summaries)
- [ ] Implement management reports (dashboard, daily/monthly business summary, sales trends, performance metrics, expense trends, inventory trends, outstanding summary, exception summary)
- [ ] Ensure all reports support date filtering, employee filtering, nozzle filtering, etc.
- [ ] Create report generation services

## Phase 17: Printing System
- [ ] Implement print preview functionality
- [ ] Enable PDF export for all reports
- [ ] Enable Excel export for all reports
- [ ] Enable CSV export where appropriate
- [ ] Implement professional report formatting
- [ ] Support direct printer output via PySide6
- [ ] Create printable documents (sales receipts, shift reports, daily reports, reconciliation reports, attendance reports, employee reports, purchase reports, supplier invoices, customer statements, expense reports, inventory reports, management summaries)
- [ ] Create print configuration management

## Phase 18: Backup & Recovery
- [ ] Implement automatic scheduled backups
- [ ] Implement manual backup functionality
- [ ] Create backup before database migration
- [ ] Implement backup verification
- [ ] Create backup history tracking
- [ ] Implement restore capability
- [ ] Configure backup location (local disk, external USB, network folder)
- [ ] Implement database integrity checks
- [ ] Create recovery workflow documentation
- [ ] Implement backup failure detection
- [ ] Create backup encryption (optional)

## Phase 19: Testing
- [ ] Create unit tests for all modules
- [ ] Create integration tests for key workflows
- [ ] Test authentication and RBAC
- [ ] Test sales and payment processing
- [ ] Test inventory and fuel reconciliation
- [ ] Test shift opening and closing
- [ ] Test nozzle assignment
- [ ] Test attendance tracking
- [ ] Test HR functionality
- [ ] Test report generation
- [ ] Test printing functionality
- [ ] Test backup and restore
- [ ] Test database integrity
- [ ] Test error handling
- [ ] Test edge cases (internet unavailable, computer restart during transaction, etc.)

## Phase 20: Packaging & Deployment
- [ ] Create PyInstaller build configuration
- [ ] Create Windows executable
- [ ] Create installer package
- [ ] Implement configuration system
- [ ] Initialize database on first run
- [ ] Create default directories (backups, logs, reports)
- [ ] Package user documentation
- [ ] Package administrator documentation
- [ ] Package recovery documentation
- [ ] Create release process

## Phase 21: Pilot Deployment & Feedback
- [ ] Deploy to test petrol pump location
- [ ] Collect user feedback
- [ ] Fix identified issues
- [ ] Optimize performance
- [ ] Refine user interface
- [ ] Validate offline operation
- [ ] Validate backup/restore procedures
- [ ] Validate reporting accuracy

## Phase 22: Final Release
- [ ] Incorporate pilot feedback
- [ ] Perform final testing
- [ ] Update documentation
- [ ] Create final release package
- [ ] Provide deployment instructions
- [ ] Create support documentation

## Feature Definition of Done
A feature is complete only when:
- [ ] Business logic implemented
- [ ] Database layer completed
- [ ] UI components created
- [ ] Validation implemented
- [ ] Permissions checked
- [ ] Audit logging added
- [ ] Error handling implemented
- [ ] Tests written and passing
- [ ] Documentation updated
- [ ] Report integration completed (where applicable)
- [ ] Backup implications considered
- [ ] PROJECT_CONTEXT.md updated
- [ ] Git commit created
- [ ] GitHub issue updated

## Current Focus
Phase 8 (Nozzle Management) is complete end to end — service layer and UI, tested (128/128 tests passing project-wide). Phases 4-8 are all done. The user's team is reviewing the running app before deciding on further changes.

## Next Immediate Tasks
1. Migrate `Attendance.shift_label` (free text) to a real foreign key against the now-existing `Shift` model
2. Expand the `ROLE_PERMISSIONS` matrix in app/core/constants.py as each new module is implemented
3. Consider revisiting `Fuel` model's `Float` fields for money/quantity before real financial data is stored
4. Begin Phase 9 (Tank & Inventory Management) once the team's feedback on Phases 4-8 comes back

## Long-term Considerations (Not for Initial Release)
While building for offline-only operation, the architecture should not prevent future expansion:
- Keep business logic separated from UI
  - Web application possibility
- Keep repositories separated
  - Cloud synchronization possibility
- Use UUIDs
  - Merge conflict resolution possibility
- Keep domain models clean
  - Mobile application possibility
- Proper audit trails
  - Fraud detection possibility
- Normalized database relationships
  - IoT tank sensors possibility
- Modular architecture
  - Dispenser integration possibility
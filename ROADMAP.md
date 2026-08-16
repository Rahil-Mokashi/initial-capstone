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
- [x] Create user management (User model since Phase 3; full provisioning UI added 2026-08-15 per user request — `app/services/user_service.py` + `app/ui/user_management_window.py`: create logins for any of the six roles, multiple users per role, activate/deactivate/unlock/change-role, all reason-required and audit-logged; gated on `Permission.USER_MANAGE`, visible only to ADMIN/OWNER)
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
- [x] Enforce site layout rule confirmed by the user: every dispenser has exactly 2 nozzles (`MAX_NOZZLES_PER_DISPENSER`, `NozzleService.create_nozzle` rejects a 3rd)
- [x] Track fuel types per nozzle (Nozzle.fuel_id FK to the existing Fuel model; Petrol/Diesel/Power seeded by default per the user's confirmed business rule)
- [x] Implement nozzle status (active, inactive, maintenance — NozzleStatus enum; only "active" nozzles can be assigned; set_nozzle_status requires a reason and is audit-logged)
- [x] Create nozzle assignment history (NozzleAssignment rows persist per shift; no dedicated history/report view yet)
- [x] Track opening/closing meter readings (NozzleAssignment.opening_meter/closing_meter, closing validated >= opening)
- [x] Prevent duplicate nozzle assignments (enforced in ShiftService.assign_nozzle — see Phase 7)
- [x] Attendant self-service assignment view (user-raised gap, 2026-08-15): new `Permission.MY_ASSIGNMENT_VIEW` granted to `UserRole.ATTENDANT`; `ShiftService.get_my_active_assignment` + `app/ui/my_shift_window.py` let a logged-in attendant see their own current nozzle/fuel/dispenser assignment (previously an empty dashboard)
- [~] Nozzle reports: fuel-type-sectioned summary (active nozzle counts per Petrol/Diesel/Power) done via `ReportService.get_fuel_type_summary` + `app/ui/report_window.py`, with Print/PDF/Excel export (`app/services/report_export.py`, 2026-08-16); a dedicated assignment-history report is still deferred to Phase 16
- [x] Full Dispenser/Nozzle master-data UI (app/ui/nozzle_window.py: tabbed Dispensers/Nozzles, add forms, status-change with reason; deactivating a nozzle currently assigned in an open shift is blocked)

## Phase 9: Tank & Inventory Management (Complete except reports, deferred to Phase 16)
- [x] Create tank master data (Tank model + TankService.create_tank/set_tank_status, app/ui/tank_window.py)
- [x] Track fuel types and capacity (Tank.fuel_id FK to Fuel; capacity validated on create and on every transaction)
- [x] Record tank dimensions and calibration (Tank.calibration_info free-text field)
- [x] Implement dip reading tracking (TankReading: employee, optional shift, dip value, physical stock, remarks — never silently changes book stock)
- [x] Track current stock levels (Tank.current_stock, moved only by recorded transactions)
- [x] Record tank transactions (receipts, issues, adjustments — TankTransactionType; receipts/issues validated against capacity/negative stock, adjustments require a reason)
- [x] Implement fuel reconciliation (FuelReconciliation: Expected = Opening + Received - Sold, compared against a physical reading, variance classified via configurable thresholds — NORMAL/WARNING/INVESTIGATION_REQUIRED/APPROVAL_REQUIRED, never assumed to be theft; accepted reconciliation becomes the new baseline for the next period)
- [~] Tank inventory reports: fuel-type-sectioned summary (tank count/capacity/current stock and worst reconciliation variance per Petrol/Diesel/Power) done via `ReportService.get_fuel_type_summary` + `app/ui/report_window.py`, with Print/PDF/Excel export (`app/services/report_export.py`, 2026-08-16); a dedicated transaction-history report is still deferred to Phase 16

## Phase 10: Procurement Management (Complete except dedicated procurement reports, deferred to Phase 16)
- [x] Create supplier master data (`Supplier` model, `ProcurementService.create_supplier`, never hard-deleted - deactivated with a reason instead)
- [x] Implement purchase order creation (`PurchaseOrder`/`PurchaseOrderItem`, sequential `PO-0001` numbering, multi-fuel-type line items, rejects inactive suppliers/unknown fuel types)
- [x] Track fuel delivery process (`FuelDelivery`: Tanker Arrival -> Document Verification -> Fuel Quality Verification -> Pre-Dip -> Unloading -> Post-Dip -> Inventory Update, each a real status transition, audit-logged)
- [x] Implement delivery verification (document verification and quality verification are separate, ordered steps - can't skip ahead)
- [x] Create fuel quality verification tracking (`quality_verified_by_id`/`quality_verified_at`/`quality_notes`, plus a `reject_delivery` path with a required reason for a failed check)
- [x] Record pre-dip and post-dip readings (both create real `TankReading` rows via `TankService.record_reading` - not a parallel/duplicate reading mechanism)
- [x] Update inventory on delivery (`quantity_received` is *derived* from post-dip minus pre-dip, then creates a real Tank RECEIPT `TankTransaction` via `TankService.record_transaction` - the same capacity-checked, audited path every other receipt uses)
- [x] Create supplier invoice management (`SupplierInvoice`, status derived from payments - never set directly)
- [x] Implement supplier payment tracking (`SupplierPayment`, partial payments supported, rejects payment beyond the outstanding balance, rejects paying an already-fully-paid invoice)
- [ ] Create procurement reports (deferred to Phase 16, matching every other module's reports)

## Phase 11: Sales Management (Complete except dedicated sales reports and printable receipts, deferred to Phases 16/17)
User requirement confirmed 2026-08-16: fuel prices change over time (Petrol/Diesel/Power each priced independently, per the confirmed nozzle/fuel-type business rules), so every Sale must snapshot its own `rate_per_liter` and `amount` at the moment of the transaction, never a live reference to `Fuel.rate_per_liter`. This is the same pattern already established for `PurchaseOrderItem.rate_per_liter` in Phase 10 (locked in at order time, not looked up live) - reuse it rather than re-deciding it. Without this, a credit customer's amount owed would silently change every time the pump's fuel prices change, which is a real data-integrity bug, not just a cosmetic one - it's the whole reason Phase 13's credit tracking needs this to already be correct in Sale before it can trust it.
- [x] Create sale recording functionality (`Sale` model, `SaleService.create_sale`, `app/ui/sales_window.py`)
- [x] Track sale details (`sale_at`, `shift_id`, `employee_id`, `nozzle_id`, `fuel_id` all captured per sale)
- [x] Record quantity, rate, and amount - **rate/amount are a snapshot at sale time, not a live lookup** (see note above); each sale posts a real Tank ISSUE `TankTransaction` via the permission-layered `TankService.record_transaction_as_related_action`, the same audited path every other stock movement uses
- [x] Support multiple payment methods (cash, UPI, card, credit - `PaymentMethod` enum; CREDIT requires a `customer_id`)
- [x] Prevent duplicate sales (sequential unique `receipt_number` via `SaleRepository.next_receipt_number`; no separate fuzzy-duplicate detection was requested or built)
- [x] Implement sale cancellation/reversal workflow (`cancel_sale`: requires a reason, only from COMPLETED, posts a compensating tank ADJUSTMENT and sets `reversal_transaction_id` - never deletes the original sale)
- [x] Track customer information where applicable (`Customer` model + `SaleService` customer CRUD, linked via `Sale.customer_id`)
- [~] Generate sales receipts (sequential `receipt_number` generated on every sale; a printable/PDF receipt document is deferred to Phase 17 Printing, matching every other module's print/export work)
- [ ] Create sales reports (deferred to Phase 16, matching every other module's reports)

Also resolved as part of this phase: a real permission-layering bug where `TankService.record_transaction`/`record_reading` required `INVENTORY_MANAGE`, which blocked attendants (who only hold `SALE_MANAGE`) from recording sales at all, since `SaleService.create_sale` calls those methods internally as a side effect of a sale the attendant *is* authorized to make. Fixed via a public/related-action/private three-way method split (`record_transaction` stays permission-checked for direct callers; `record_transaction_as_related_action` is unchecked for calls already authorized by the calling service's own check; `_record_transaction` holds the shared logic) - the same pattern should be reused for any future service (Reconciliation, Expense) that triggers `TankService` side effects on behalf of a lower-privileged actor. Also added a nullable `Nozzle.tank_id` (with a documented single-active-tank-per-fuel fallback in `SaleService._resolve_tank_id`) to resolve which tank a nozzle's sale should draw down, since a pump can have multiple tanks per fuel type.

## Phase 12: Payment Management (Complete except reconciliation workflows/reports, deferred to Phases 15/16)
Every `Sale` now creates its own `Payment` record (problemstatement.md #17) - settlement is tracked separately from the sale itself, since fuel can be dispensed (a completed sale) while money is still owed or the transaction later found to have failed. `Payment` lives in `app/services/sale_service.py` rather than a standalone service since it's a 1:1 satellite of Sale, created/reversed on the exact same `SALE_MANAGE` permission at the exact same moments - the same reasoning already used to fold Customer CRUD into `SaleService`.
- [x] Track cash payments separately (`Payment.method = "cash"`, status `SUCCESS` immediately - cash is collected at the point of sale)
- [x] Track UPI payments with reference numbers (`Payment.reference_number`, entered on the sale form when the method is UPI)
- [x] Track card payments with authorization codes (same `Payment.reference_number` field, used for the card's authorization code)
- [x] Track credit sales separately (`Payment.method = "credit"`, status starts `PENDING` rather than `SUCCESS` - settled later via Phase 13's customer payments)
- [x] Implement payment status tracking (success, pending, failed, reversed, refunded) - `PaymentStatus` enum; `mark_payment_failed`/`refund_payment` (both require a reason, audit-logged, never a silent overwrite) cover the after-the-fact correction cases (e.g. a card declines after fuel is already dispensed); cancelling a sale automatically reverses its payment
- [ ] Create payment reconciliation workflows (deferred to Phase 15, once the full cash/UPI/card shift-close reconciliation this depends on exists)
- [x] Track payment responsibility by attendant (`Payment.attendant_id`, `Payment.shift_id` - matches problemstatement.md #17's required fields)
- [ ] Create payment reports (deferred to Phase 16, matching every other module's reports)

## Phase 13: Credit Management (Complete except the fuel-type-sectioned/aging reports, deferred to Phase 16)
User requirement confirmed 2026-08-16: full lifecycle tracking for credit customers ("crediters") - who they are, whether they've paid, and their activity broken down by fuel type (Petrol/Diesel/Power), matching the same per-fuel-type reporting pattern already established for tanks/nozzles (`ReportService.get_fuel_type_summary`). A credit sale is a Sale (Phase 11) with payment_method=CREDIT, so its fuel type comes for free from the sale's own nozzle->fuel link - Phase 13 doesn't need a separate fuel-tracking mechanism, just a report that groups Sale/CustomerPayment data by that existing link, the same way Phase 16's reports will.
- [x] Create customer master data (`Customer` model - built in Phase 11, since a credit sale needs a customer to exist first)
- [x] Implement credit account management (`CreditAccount`: one per customer, tracks `credit_limit`/`payment_due_days`; a customer with no account cannot be sold to on credit at all - opting in is a deliberate step)
- [x] Set credit limits (`CreditService.set_credit_limit` - reason required, audit-logged, same pattern as every other status/limit change in this app)
- [x] Track credit sales (no separate `CreditSale` table needed - a `Sale` with `payment_method=CREDIT` already carries everything; `CreditService` reads `SaleRepository.list_by_customer` directly rather than duplicating the sale record)
- [x] Record customer payments (`CustomerPayment`, one row per payment, never edited/deleted - the same append-only rule already applied to `SupplierPayment`, a correction is a new record)
- [x] Calculate outstanding balances (`CreditService.get_outstanding_balance` recomputes credit-sales-total minus payments-total from scratch on every call, never stored/incremented - same "recompute from scratch, never let it drift" approach used for `SupplierInvoice.status`/`PurchaseOrder.status`. Each credit sale's amount comes from the Sale's own snapshotted rate/amount (Phase 11) - never recalculated against today's fuel price)
- [x] Implement credit blocking when limit exceeded (`SaleService.create_sale` calls `CreditService.ensure_credit_available` for every CREDIT sale, deliberately undecorated/unchecked - the same reasoning as `TankService`'s `*_as_related_action` split, since the credit check is a side effect of an action the acting attendant is already authorized to perform, not a separate "view credit accounts" action)
- [x] Generate customer statements (`CreditService.get_customer_statement` - every credit sale and payment for a customer, sorted by date, with a running balance; `CustomerStatementDialog` in `app/ui/credit_window.py`)
- [x] Track overdue amounts (`CreditAccount.payment_due_days`; `CreditService.is_overdue` flags an account whose oldest unpaid credit sale is older than that window - a graduated signal, never an accusation, matching the same principle already applied to fuel reconciliation variance)
- [ ] **Fuel-type-sectioned credit reports** (explicit user requirement, 2026-08-16): deferred to Phase 16 alongside every other module's dedicated reports - the per-customer statement above already gives a working view of the same data in the meantime
- [ ] Create the rest of the credit reports listed in problemstatement.md #18/#31 (aging, top debtors, etc.) - deferred to Phase 16

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
- [ ] **User requirement (2026-08-15): every fuel-related report must be sectioned by fuel type** (a Petrol section, a Diesel section, a Power section), not just shown as an aggregate total. Tank/Nozzle already carry `fuel_id`, so the grouping data exists — this is a report-layer requirement to keep in mind for every report below that touches fuel volumes/stock/sales.
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

## Phase 20: Packaging & Deployment (Started early, 2026-08-15, at the user's request — needed a build to hand to their team)
- [x] Create PyInstaller build configuration (`petrol_pump_erp.spec`, `requirements-build.txt`)
- [x] Create Windows executable (`pyinstaller petrol_pump_erp.spec` → single-file `dist/PetrolPumpERP.exe`, ~90MB, verified on a simulated fresh PC — no Python or dependencies required on the target machine)
- [ ] Create installer package (currently a standalone .exe, not a proper installer with Start Menu entry/uninstaller)
- [ ] Implement configuration system
- [x] Initialize database on first run (already worked in dev; the packaging effort's real find was that the *path resolution* needed fixing — see below)
- [ ] Create default directories (backups, logs, reports)
- [ ] Package user documentation
- [ ] Package administrator documentation
- [ ] Package recovery documentation
- [ ] Create release process

**Bug found and fixed while packaging**: `app/database/connection.py` resolved the DB path relative to its own file location, which works fine in a normal checkout but breaks under a PyInstaller onefile build — that kind of build re-extracts to a *new* temp directory on every single launch, so the database would have silently reset every time the app started. Fixed by detecting the frozen state (`sys.frozen`) and using a stable per-user directory (`%LOCALAPPDATA%\PetrolPumpERP`) instead. Verified end-to-end against a simulated fresh PC (empty fake `LOCALAPPDATA`): the app created its database in the right place and the login screen rendered correctly. Covered by `tests/test_core_setup.py`.

**Build-size tradeoff**: tried excluding matplotlib/PIL/tkinter (pulled in as false-positive transitive candidates, not actually used by this app) to shrink the ~94MB build. That broke PySide6's Qt platform-plugin bundling — the packaged app exited silently right after startup with no window and no error, because matplotlib's Qt-backend hook turns out to be what triggers PyInstaller's fuller PySide6 plugin collection. Reverted; documented in the spec file so nobody re-attempts this without knowing why it fails.

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
Phases 1-13 are complete end to end (Auth/RBAC, Employee/HR, Attendance, Shift, Nozzle, Tank & Inventory, Procurement, Sales, Payments, Credit Management), plus the attendant self-service "My Shift" view, fuel-type-sectioned (Petrol/Diesel/Power) reports, full User Management, a live dashboard KPI strip, and the 2026-08-16 build-audit resolution pass.

On 2026-08-16 the user asked for a full build audit and then to resolve everything on its priority-ranked list. Done: Alembic migrations (replacing `create_all()`), Float→Numeric/Decimal for every money/volume column, removing the dead `InventoryService`/redundant `Fuel` stock fields, password self-service + forced rotation, production file logging (plus a real Alembic-logger bug this surfaced and fixed), backup/restore with RBAC and audit logging, an audit log viewer, and PDF/Excel export + Print for the fuel-type report. Also fixed along the way: a real reconciliation bug (local/UTC day-boundary mismatch dropping same-day transactions), a user-reported Enter-key navigation gap, and a dashboard grid-wrap bug. Deferred: the shared UI base-class refactor (see PROJECT_CONTEXT.md's Pending Modules — a deliberate call to not risk a broad refactor at the end of an already large session). Phase 10 (Procurement Management) is complete end to end - full Supplier/Purchase Order/Fuel Delivery/Invoice/Payment workflow, integrated with TankService so deliveries create real Tank RECEIPT transactions through the same audited path as every other receipt. The dashboard was redesigned per explicit user feedback (grouped sections, decluttered top bar - see PROJECT_CONTEXT.md), then gained a live KPI strip (`app/services/dashboard_service.py`) — today's sales, open shifts, low-stock tanks, pending purchase orders, each gated on the same permission its module already uses - as the first concrete step of the standing self-analysis/dashboard pass. Phase 11 (Sales Management) is complete end to end - Sale/Customer models, snapshot pricing, cash/UPI/card/credit payment methods, cancellation with compensating tank adjustments, and a dual-path UI (full picker for Manager/Supervisor, self-service auto-resolved assignment for Attendant); this phase also fixed a real permission-layering bug in `TankService` (see Phase 11's notes above) and added `Nozzle.tank_id` to resolve tank ambiguity. Phase 12 (Payment Management) is complete - every Sale creates its own Payment record, settled separately since fuel can be dispensed while money is still owed or later found to have failed; mark_payment_failed/refund_payment cover the correction cases. Phase 13 (Credit Management) is complete - CreditAccount/CustomerPayment, outstanding balances always recomputed from scratch, credit-limit enforcement wired into SaleService.create_sale via an intentionally unchecked `ensure_credit_available` (the same reasoning as TankService's `*_as_related_action` split), customer statements with a running balance, and overdue flagging off a configurable due-days window. 369/369 tests passing project-wide, CI runs them on every push. Per the user's standing instruction to keep building autonomously without further check-ins: continue self-reviewing the app for further improvements (including offline-capable ML/analytics where it genuinely helps) alongside each phase, then continue through Phase 14 (Expense Management) onward.

## Next Immediate Tasks
1. Full-app self-analysis pass (autonomous, per standing instruction): the dashboard KPI strip is the first concrete result (see Current Focus above); keep re-reviewing the app end-to-end for further betterments, including offline-capable ML/analytics where it genuinely adds value, and implement what's found
2. Continue to Phase 12 (Payment Management — review overlap with Sale.payment_method/status, since much may already be covered), then Phase 13 (Credit Management, now unblocked), Phase 14 (Expense Management), Phase 15 (Reconciliation Management - cash/UPI/card, distinct from existing fuel reconciliation), Phase 16 (Reporting System), Phase 17 (Printing), and onward per the phase list below
3. The shared UI base-class refactor (list-window/form-dialog boilerplate), as its own focused pass
4. Migrate `Attendance.shift_label` (free text) to a real foreign key against the now-existing `Shift` model
5. Expand the `ROLE_PERMISSIONS` matrix in app/core/constants.py as each new module is implemented
6. Decide whether `ADMIN` and `OWNER` should keep identical permissions or diverge (flagged in the 2026-08-16 audit)
7. Extend PDF/Excel export to the rest of Phase 16's reports, reusing `app/services/report_export.py`'s pattern

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
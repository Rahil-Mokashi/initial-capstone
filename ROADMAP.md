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

## Phase 14: Expense Management (Complete except reconciliation/reports, deferred to Phases 15/16)
- [x] Create expense category management (`ExpenseCategory` - same name+status master-data pattern as `Supplier`, never deleted, only deactivated)
- [x] Track expense details (amount, date, employee, shift - `shift_id` nullable since not every expense happens during a shift, e.g. monthly rent)
- [x] Record payment method for expenses (cash/UPI/card - CREDIT is rejected at the schema level, since an expense being "on credit" doesn't map to any real workflow here)
- [x] Track expense receipts (`Expense.receipt_reference` - a reference string, the same lightweight pattern already used for `Payment.reference_number`/`SupplierPayment.reference`, not a file upload - nothing in this app stores attached files yet)
- [x] Implement expense approval workflow (`approve_expense`/`reject_expense`, gated on the stricter `EXPENSE_APPROVE` permission - not granted to Accountant, the same "a stricter permission for a sensitive action" pattern as `Shift.reopen_shift`'s `SHIFT_REOPEN`; rejecting requires a reason, both audit-logged; an expense is never deleted or edited once approved/rejected)
- [ ] Support expense reports / Generate expense reports (deferred to Phase 16, matching every other module's reports)
- [ ] Create expense reconciliation (deferred to Phase 15, which already has its own "expense reconciliation workflow" line item)

## Phase 15: Reconciliation Management (Complete except dedicated reports, deferred to Phase 16)
Cash/UPI/card/expense reconciliation are folded into one per-shift `ShiftReconciliation` rather than four separate mechanisms, since problemstatement.md #20 groups them together as things settled at the same point (shift close) against the same source data (that shift's own Sale/Payment/Expense records) - building four parallel workflows that all read the same data would be duplication, not four distinct features. Fuel reconciliation already exists per-tank (Phase 9, `TankService.perform_reconciliation`) and is intentionally left as-is, not merged in - it operates on a different unit (litres in a tank) on a different cadence (whenever a dip reading is taken, not necessarily per shift).
- [x] Implement cash reconciliation workflow (`ShiftReconciliation.expected_cash`/`declared_cash`/`cash_variance` - expected is computed from that shift's CASH sales minus approved CASH expenses, never a manual entry)
- [x] Implement UPI reconciliation workflow (same shape as cash, `expected_upi`/`declared_upi`/`upi_variance`)
- [x] Implement card reconciliation workflow (same shape as cash, `expected_card`/`declared_card`/`card_variance`)
- [x] Implement fuel reconciliation workflow (already existed since Phase 9 - `TankService.perform_reconciliation`, not touched here)
- [x] Implement expense reconciliation workflow (folded into the cash/UPI/card expected totals above - an *approved* expense paid during the shift reduces the expected total for whichever method it was paid with, since that money left the till before the shift was reconciled; a still-PENDING expense doesn't affect it yet)
- [x] Implement shift reconciliation workflow (`ReconciliationService.perform_shift_reconciliation` - one reconciliation per shift, rejected if the shift's already been reconciled, never edited afterward)
- [x] Create discrepancy detection workflow (`classify_reconciliation_variance` - the worst of the three payment methods' variance percentages, reusing `VarianceClassification`'s existing NORMAL/WARNING/INVESTIGATION_REQUIRED/APPROVAL_REQUIRED graduated scale rather than inventing a different one for money vs. fuel)
- [x] Create exception handling for variances (a NORMAL/WARNING classification is auto-accepted; INVESTIGATION_REQUIRED/APPROVAL_REQUIRED sets status `PENDING_APPROVAL` until a manager/owner acts on it)
- [x] Create supervisor/manager review workflow (`Permission.RECONCILIATION_MANAGE` lets a Shift Supervisor *perform* a reconciliation; `Permission.RECONCILIATION_APPROVE` - Manager/Owner only, not Supervisor or Accountant - is required to clear a `PENDING_APPROVAL` one via `approve_shift_reconciliation`; problemstatement.md #21's 7-step ticket workflow (exception -> supervisor review -> manager investigation -> explanation -> owner approval -> adjustment -> audit log) is collapsed into this single approval action with a remarks field, matching the size of every other approval workflow already built in this app - `Expense.approve_expense`, `Shift.reopen_shift` - rather than building a heavier multi-stage ticket system found nowhere else in the codebase)
- [ ] Create reconciliation reports (deferred to Phase 16, matching every other module's reports)

## Phase 16: Reporting System (partial — the specific reports every earlier phase promised are done; the much larger problemstatement.md #25-32 enumeration is not)
- [x] **User requirement (2026-08-15): every fuel-related report must be sectioned by fuel type** (a Petrol section, a Diesel section, a Power section), not just shown as an aggregate total — applied to `get_fuel_type_summary` (Phase 9), `get_sales_report`, and `get_credit_fuel_type_report`
- [x] Create report generation services (`TableReport` dataclass + generic `export_table_pdf`/`export_table_excel`/`build_table_report_html` in `app/services/report_export.py`, and a generic `TableReportWindow` in `app/ui/table_report_window.py` shared by every report below — one PDF/Excel/Print/date-filter implementation instead of one per report)
- [x] Closed out the reports every earlier phase's own docs explicitly named as "deferred to Phase 16": **Sales Report** (`get_sales_report`, fuel-type-sectioned, date-filterable), **Payment Summary Report** (`get_payment_summary_report`, by method and status), **Expense Summary Report** (`get_expense_summary_report`, by category and status), **Credit Report by Fuel Type** (`get_credit_fuel_type_report` — the explicit 2026-08-16 user requirement; "extended" is fuel-type-attributable via each sale's own nozzle->fuel link, "collected"/"outstanding" are reported at the portfolio level since payments aren't allocated to individual sales, and the report says so rather than inventing a per-fuel figure the data doesn't support), **Customer Outstanding Report** (`get_customer_outstanding_report`, per credit account), **Shift Reconciliation Report** (`get_reconciliation_report`, variance/classification per shift)
- [x] Ensure reports support date filtering where the underlying data has a meaningful date dimension (`TableReportWindow`'s optional From/To fields, wired through to `date_from`/`date_to` on the four reports where a range makes sense - Sales, Payments, Expenses, Reconciliation; the two Credit reports and the fuel-type summary are point-in-time balances, not a range)
- [x] A single "Reports" dashboard entry point (`ReportsHubWindow`) lists every report the acting user can open, gated per-report on that report's own module's permission, rather than growing the dashboard by one card per report
- [ ] Implement daily/shift/attendant/HR/inventory/management reports enumerated in problemstatement.md #25-32 (daily reports across every module, attendant-wise/nozzle-wise/fuel-wise shift breakdowns, HR reports, tank/fuel-movement inventory reports, cash book/ledger financial reports, trend/exception management reports) - a much larger set than what's built above, deliberately left for a dedicated later pass rather than attempted in the same session as five other phases
- [ ] Filter by employee/nozzle (beyond the date filtering already built) for the reports where that dimension applies

## Phase 17: Printing System (Complete for every report/document that exists so far; print configuration management and the still-unbuilt document types from Phase 16 remain open)
- [x] Implement print preview functionality (`app/ui/print_utils.py`'s `show_print_preview` - every "Print" button across the app now opens a `QPrintPreviewDialog`, not a direct-to-printer `QPrintDialog`, so Print and Print Preview are both satisfied from one entry point; replaces the print-only flow every report window had before)
- [x] Enable PDF export for all reports (already true for the fuel-type summary since the 2026-08-16 audit pass; now also true for all six Phase 16 table reports via the shared `export_table_pdf`)
- [x] Enable Excel export for all reports (same shared `export_table_excel`)
- [x] Enable CSV export where appropriate (`export_table_csv`, new - wired into every `TableReportWindow`-based report; not added to the fuel-type summary window, which predates the generic report infrastructure and stays on its own bespoke export functions)
- [x] Implement professional report formatting (the existing ReportLab/openpyxl styling - indigo header row, alternating row shading, bold headers - is shared by every report through the generic export functions, so "professional formatting" is a property of the shared layer, not something to redo per report)
- [x] Support direct printer output via PySide6 (`QPrintPreviewDialog`'s own Print action, `QPrinter(QPrinter.HighResolution)`)
- [x] Create printable documents - two concrete document types added, closing explicit promises from earlier phases: **Sales receipts** (`export_sale_receipt_pdf`/`build_sale_receipt_html`, "Print Receipt"/"Export Receipt PDF" on the Sales screen - Phase 11 had explicitly deferred this) and **Customer statements** (`CustomerStatementDialog` gained Print/Export PDF/Export Excel, reusing the `TableReport` shape by treating each statement line as a row with a trailing running-balance row) - the rest of the list (shift/daily/attendance/employee/purchase/supplier-invoice/inventory/management documents) depends on report types Phase 16 hasn't built yet and is deferred alongside them
- [ ] Create print configuration management (default printer, paper size, margins, letterhead) - not attempted; every print/export function currently uses sensible fixed defaults (A4, standard margins) rather than a configurable settings screen

## Phase 18: Backup & Recovery (Complete except configurable location, recovery-doc, and optional encryption)
Manual backup, pre-migration backup, backup history, and restore all already existed from the 2026-08-16 audit-resolution pass - this phase closed the remaining gaps rather than rebuilding what was already there.
- [x] Implement automatic scheduled backups (`should_take_scheduled_backup` - a backup is taken on app startup whenever the most recent one, of any reason, is older than `AUTO_BACKUP_INTERVAL_HOURS` (24h); checked relative to the last backup actually taken rather than a fixed time of day, since a desktop app isn't always running to hit one)
- [x] Implement manual backup functionality (already existed - `BackupService.create_backup`, "Back Up Now" button)
- [x] Create backup before database migration (already existed - `init_db()`'s pre-migration backup)
- [x] Implement backup verification (`create_backup` now runs `run_integrity_check` against the *backup file itself* immediately after creating it and raises if it's not sound, rather than trusting the SQLite backup API succeeded and only finding out during a real restore emergency)
- [x] Create backup history tracking (already existed - `list_backups`)
- [x] Implement restore capability (already existed - `BackupService.restore_backup`, with its own pre-restore safety backup)
- [ ] Configure backup location (local disk, external USB, network folder) - not attempted; every backup still goes to the fixed `<db_dir>/backups` folder, since making this configurable needs a settings screen that doesn't exist yet
- [x] Implement database integrity checks (`run_integrity_check` - `PRAGMA integrity_check` against a fresh connection; a new "Check Integrity" button on the Backups screen, audit-logged either way)
- [ ] Create recovery workflow documentation - not attempted this pass
- [x] Implement backup failure detection (both the pre-migration and scheduled backup attempts in `init_db()` are wrapped so a failure - disk full, permission denied, or now a failed verification - is logged and never blocks the app from starting; `BackupWindow`'s existing error handling already surfaced manual/restore failures to the user)
- [ ] Create backup encryption (optional) - not attempted, explicitly marked optional in the original scope

## Phase 19: Testing (largely already satisfied incrementally - this pass adds the one thing that was genuinely missing: a real integration test)
Every module in this app was built with its own unit tests as part of the phase that built it (435 tests total by the end of this pass), so most of this checklist has been true for a while without a dedicated "testing phase" - the one real gap was that every test exercised one service (or one UI window) in isolation, so a wiring mistake between services (the exact class of bug the TankService/SaleService permission-layering issue was) could in principle pass every individual test suite while still being broken end-to-end.
- [x] Create unit tests for all modules (true since each phase's own tests - 435 tests across `tests/`)
- [x] Create integration tests for key workflows (`tests/test_integration_full_shift_workflow.py` - wires every service the same way `AppController` does, not in isolation, and runs a full pump-day lifecycle: open shift -> assign nozzle -> cash sale + credit sale -> approve an expense -> close the shift -> reconcile -> verify the sales report, the customer's outstanding balance, and the tank's stock all independently agree with what actually happened. One thorough example, not exhaustive coverage of every possible workflow combination)
- [x] Test authentication and RBAC (`tests/test_auth_rbac.py`, plus permission checks embedded in every other service's own tests)
- [x] Test sales and payment processing (`tests/test_sale_service.py`, `tests/test_credit_service.py`)
- [x] Test inventory and fuel reconciliation (`tests/test_tank_service.py`)
- [x] Test shift opening and closing (`tests/test_shift_service.py`)
- [x] Test nozzle assignment (`tests/test_shift_service.py`, `tests/test_nozzle_service.py`)
- [x] Test attendance tracking (`tests/test_attendance_service.py`)
- [x] Test HR functionality (`tests/test_employee_service.py`)
- [x] Test report generation (`tests/test_report_service.py`, `tests/test_report_service_tables.py`)
- [x] Test printing functionality (`tests/test_report_export.py`'s PDF/Excel/CSV/HTML-building tests, plus the print-button wiring tests in `tests/test_sales_ui.py`/`tests/test_credit_ui.py` - the modal `QPrintPreviewDialog` itself isn't invoked in a headless test run, only the HTML it's given and the code path that opens it)
- [x] Test backup and restore (`tests/test_backup_restore.py`, `tests/test_backup_service.py`, `tests/test_backup_ui.py`)
- [x] Test database integrity (`tests/test_backup_restore.py`'s `run_integrity_check` tests, including the corrupted-file case)
- [x] Test error handling (every service test file covers its `AppError`/`ValueError`/`PermissionDeniedError` paths; every UI dialog's generic `except Exception` fallback is exercised where it was added during the 2026-08-16 audit pass)
- [ ] Test edge cases like "computer restart during transaction" - not attempted; SQLAlchemy's transaction boundaries + `safe_commit`'s rollback-on-failure already provide this at the framework level, but no test explicitly simulates a mid-write crash. "Internet unavailable" isn't a meaningful test for this app - it has no network dependency to begin with, by design

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
Phases 1-15 are complete end to end (Auth/RBAC, Employee/HR, Attendance, Shift, Nozzle, Tank & Inventory, Procurement, Sales, Payments, Credit Management, Expense Management, Reconciliation Management), plus the attendant self-service "My Shift" view, full User Management, a live dashboard KPI strip, and the 2026-08-16 build-audit resolution pass. Phases 16 (Reporting), 17 (Printing), and 18 (Backup & Recovery) are each mostly complete, and Phase 19 (Testing) is effectively complete - see each phase's own section above. 435/435 tests passing project-wide. Phase 20 (Packaging & Deployment) has its core deliverable (the standalone .exe) done, with an installer/config-system/packaged-docs remaining as legitimate further code work. **Phases 21 and 22 (Pilot Deployment & Feedback, Final Release) require the user's real-world deployment and feedback and cannot be completed autonomously - they are the natural stopping point for what an agent can build alone.**

On 2026-08-16 the user asked for a full build audit and then to resolve everything on its priority-ranked list. Done: Alembic migrations (replacing `create_all()`), Float→Numeric/Decimal for every money/volume column, removing the dead `InventoryService`/redundant `Fuel` stock fields, password self-service + forced rotation, production file logging (plus a real Alembic-logger bug this surfaced and fixed), backup/restore with RBAC and audit logging, an audit log viewer, and PDF/Excel export + Print for the fuel-type report. Also fixed along the way: a real reconciliation bug (local/UTC day-boundary mismatch dropping same-day transactions), a user-reported Enter-key navigation gap, and a dashboard grid-wrap bug. Deferred: the shared UI base-class refactor (see PROJECT_CONTEXT.md's Pending Modules — a deliberate call to not risk a broad refactor at the end of an already large session). Phase 10 (Procurement Management) is complete end to end - full Supplier/Purchase Order/Fuel Delivery/Invoice/Payment workflow, integrated with TankService so deliveries create real Tank RECEIPT transactions through the same audited path as every other receipt. The dashboard was redesigned per explicit user feedback (grouped sections, decluttered top bar - see PROJECT_CONTEXT.md), then gained a live KPI strip (`app/services/dashboard_service.py`) — today's sales, open shifts, low-stock tanks, pending purchase orders, each gated on the same permission its module already uses - as the first concrete step of the standing self-analysis/dashboard pass. Phase 11 (Sales Management) is complete end to end - Sale/Customer models, snapshot pricing, cash/UPI/card/credit payment methods, cancellation with compensating tank adjustments, and a dual-path UI (full picker for Manager/Supervisor, self-service auto-resolved assignment for Attendant); this phase also fixed a real permission-layering bug in `TankService` (see Phase 11's notes above) and added `Nozzle.tank_id` to resolve tank ambiguity. Phase 12 (Payment Management) is complete - every Sale creates its own Payment record, settled separately since fuel can be dispensed while money is still owed or later found to have failed; mark_payment_failed/refund_payment cover the correction cases. Phase 13 (Credit Management) is complete - CreditAccount/CustomerPayment, outstanding balances always recomputed from scratch, credit-limit enforcement wired into SaleService.create_sale via an intentionally unchecked `ensure_credit_available` (the same reasoning as TankService's `*_as_related_action` split), customer statements with a running balance, and overdue flagging off a configurable due-days window. Phase 14 (Expense Management) is complete - ExpenseCategory/Expense, a stricter EXPENSE_APPROVE permission not granted to Accountant (mirroring Shift.reopen_shift's SHIFT_REOPEN split), reject requiring a reason, expenses never edited once approved/rejected. Phase 15 (Reconciliation Management) is complete - cash/UPI/card/expense reconciliation folded into one per-shift ShiftReconciliation (never four separate mechanisms, since they're all settled from the same shift's Sale/Payment/Expense data), reusing the existing VarianceClassification graduated-severity scale, with a Supervisor-performs/Manager-approves split matching problemstatement.md #21's discrepancy workflow collapsed into a single approval action. Phase 16 (Reporting System) is partially complete - six new reports (Sales, Payment Summary, Expense Summary, Credit by Fuel Type, Customer Outstanding, Shift Reconciliation) close out every "deferred to Phase 16" promise made by name in Phases 10-15's own docs, sharing one generic TableReport/TableReportWindow/export implementation and a single Reports hub rather than a bespoke window per report; the much larger problemstatement.md #25-32 enumeration is deliberately left for a dedicated later pass. Phase 17 (Printing System) is also complete for everything that exists today - `app/ui/print_utils.py`'s `show_print_preview` gives every report a real `QPrintPreviewDialog` instead of a direct-to-printer dialog, CSV export was added, and two new printable documents (sales receipts, customer statements) close promises Phase 11/13 deferred to this phase. Phase 18 (Backup & Recovery) is also complete except configurable location/documentation/encryption - backups now verify themselves via integrity check the moment they're created, a scheduled backup is taken on startup once the last one is more than 24h old, and a "Check Integrity" button runs `PRAGMA integrity_check` on demand. Phase 19 (Testing) was largely already satisfied incrementally by every module's own tests; the one real gap closed was `tests/test_integration_full_shift_workflow.py`, a genuine cross-service integration test wiring every service the way `AppController` does and running a full pump-day lifecycle end to end. 435/435 tests passing project-wide, CI runs them on every push. Phase 20 (Packaging) already has its core deliverable done (the standalone .exe); an installer, config system, and packaged docs remain as legitimate further work. Phases 21-22 (Pilot Deployment, Final Release) require the user's real-world deployment and feedback and are not something an agent can complete autonomously - see Next Immediate Tasks below for what's left that's actually agent-doable.

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
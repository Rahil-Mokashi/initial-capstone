# Petrol Pump ERP - Problem Statement

## Overview

This document defines the requirements for a **Petrol Pump Management ERP** system. The system is designed to be deployed on a petrol pump desktop computer and must operate reliably even when there is NO INTERNET CONNECTION. This is a real-world production application, NOT a student CRUD project.

---

## 1. FINAL PROJECT SCOPE

The system consists ONLY of:

1. Desktop Application
2. Local Database
3. Local Backup System
4. Reporting System
5. Printing System

**There is NO requirement for:**
- Web application
- Remote monitoring
- Cloud dashboard
- AWS deployment
- Cloud database
- Online synchronization
- Mobile application
- Remote owner access

**Do NOT introduce these technologies unless explicitly requested later.**

The entire application must work offline.

---

## 2. PRIMARY OBJECTIVE

Build a complete Petrol Pump Management ERP capable of managing:

- Petrol pump operations
- Fuel procurement
- Fuel inventory
- Tank management
- Tank readings
- Dispensers
- Nozzles
- Daily nozzle assignment
- Attendant management
- Shift management
- Sales
- Cash
- UPI
- Card
- Credit sales
- Customers
- Customer outstanding
- Supplier management
- Supplier payments
- Expenses
- Cash reconciliation
- Fuel reconciliation
- Shift reconciliation
- Employee management
- Employee attendance
- Employee performance
- HR records
- Leave
- Reports
- Printing
- Backup
- Audit logs
- User permissions
- Notifications/alerts
- System configuration

---

## 3. TECHNOLOGY STACK

**Python 3.13+**

**Desktop:**
- PySide6

**Database:**
- SQLite

**ORM:**
- SQLAlchemy 2.x

**Database migrations:**
- Alembic

**Validation:**
- Pydantic

**Testing:**
- pytest

**PDF:**
- ReportLab

**Excel:**
- openpyxl

**Configuration:**
- pydantic-settings

**Logging:**
- Python logging with structured logging

**Packaging:**
- PyInstaller

**Version control:**
- Git + GitHub

**Do NOT use Java.**
**Do NOT use Electron.**
**Do NOT use a web application framework.**

---

## 4. ARCHITECTURE

**Use a clean modular desktop architecture.**

Recommended architecture:

```
Presentation Layer
    ↓
Application/Service Layer
    ↓
Domain Layer
    ↓
Repository Layer
    ↓
SQLAlchemy
    ↓
SQLite
```

**Key architectural principles:**

- Do NOT put business logic directly inside UI widgets.
- Do NOT put SQL queries everywhere.
- Use repositories and services.

---

## 5. PROJECT STRUCTURE

Create the following directory structure:

```
petrol-pump-erp/
├── app/
│   ├── main.py
│   │
│   ├── core/
│   │   ├── config.py
│   │   ├── security.py
│   │   ├── logging.py
│   │   ├── exceptions.py
│   │   └── constants.py
│   │
│   ├── database/
│   │   ├── connection.py
│   │   ├── session.py
│   │   ├── base.py
│   │   └── migrations/
│   │
│   ├── models/
│   │
│   ├── repositories/
│   │
│   ├── services/
│   │
│   ├── schemas/
│   │
│   ├── ui/
│   │   ├── windows/
│   │   ├── dialogs/
│   │   ├── widgets/
│   │   └── components/
│   │
│   ├── modules/
│   │   ├── authentication/
│   │   ├── employees/
│   │   ├── attendance/
│   │   ├── shifts/
│   │   ├── nozzles/
│   │   ├── tanks/
│   │   ├── inventory/
│   │   ├── procurement/
│   │   ├── suppliers/
│   │   ├── sales/
│   │   ├── payments/
│   │   ├── customers/
│   │   ├── credit/
│   │   ├── expenses/
│   │   ├── reconciliation/
│   │   ├── hr/
│   │   ├── reports/
│   │   ├── printing/
│   │   ├── backups/
│   │   └── audit/
│   │
│   └── utils/
│
├── tests/
│
├── docs/
│
├── scripts/
│
├── backups/
│
├── reports/
│
├── .github/
│
├── README.md
├── PROJECT_CONTEXT.md
├── CLAUDE.md
├── ARCHITECTURE.md
├── ROADMAP.md
├── CHANGELOG.md
├── CONTRIBUTING.md
└── SECURITY.md
```

---

## 6. BUSINESS ROLES

Implement the following business roles:

- **ADMIN**
- **OWNER**
- **MANAGER**
- **ACCOUNTANT**
- **SHIFT_SUPERVISOR**
- **ATTENDANT**

**Optionally:**
- **HR_MANAGER** (if the client requires a separate HR user)

**Use RBAC. Never hard-code permissions throughout the application.**

---

## 7. ATTENDANT MANAGEMENT

Every attendant is an employee.

Track the following for every attendant:

- Employee ID
- Name
- Contact
- Joining date
- Designation
- Status
- Department
- Documents
- Emergency contact
- Assigned outlet
- Role

**Every attendant must have:**
- Attendance
- Shift history
- Nozzle assignment history
- Sales history
- Payment responsibility
- Reconciliation history
- Performance metrics
- Exceptions

---

## 8. DAILY NOZZLE ASSIGNMENT

Every shift must assign attendants to nozzles.

**Example - Morning Shift:**
```
Attendant A → Nozzle 1
Attendant B → Nozzle 2
Attendant C → Nozzle 3
Attendant D → Nozzle 4
```

**Create a NozzleAssignment table with fields:**
- Assignment ID
- Employee ID
- Nozzle ID
- Shift ID
- Date
- Start time
- End time
- Opening meter
- Closing meter
- Assigned by
- Status
- Remarks

**Prevention rules:**
- Duplicate active assignment
- Two attendants on same nozzle
- Conflicting assignments
- Unauthorized reassignment

**All changes must be audited.**

---

## 9. ATTENDANCE

**Track:**
- Present
- Absent
- Late
- Half Day
- Leave
- Holiday
- Overtime-ready fields

**Record:**
- Check-in
- Check-out
- Shift
- Employee
- Supervisor
- Date
- Correction reason

**Attendance correction requires authorization.**

---

## 10. HR MODULE

Include:
- Employee master
- Employee documents
- Attendance
- Leave
- Shift history
- Nozzle assignments
- Performance
- Disciplinary/incident records where appropriate
- Employee status
- Joining/exit information

**Do NOT tightly couple HR logic to sales.**

---

## 11. SHIFT MANAGEMENT

**Implement the following workflow:**

1. **SHIFT OPEN**
   - Employee Attendance
   - Nozzle Assignment
   - Opening Meter Reading
   - Sales
   - Cash
   - UPI
   - Card
   - Credit Sales
   - All collection

2. **Closing Meter Reading**
   - Record closing meter
   - Cash Reconciliation
   - UPI Reconciliation
   - Card Reconciliation
   - Fuel Reconciliation
   - Expense Reconciliation
   - Supervisor Review
   - Manager Review if required

3. **SHIFT CLOSED**
   - A finalized shift must not be freely edited.
   - Use controlled reopening/adjustment workflows.

---

## 12. FUEL PROCUREMENT

**Implement the following workflow:**

1. Fuel Requirement
2. Purchase
3. Tanker Arrival
4. Document Verification
5. Fuel Quality Verification
6. Pre-Dip Reading
7. Fuel Unloading
8. Post-Dip Reading
9. Inventory Update
10. Invoice
11. Supplier Payment

---

## 13. TANK MANAGEMENT

**Track the following for every tank:**
- Tank
- Fuel type
- Capacity
- Current stock
- Opening stock
- Closing stock
- Dip readings
- Calibration information
- Tank transactions

**Every reading must include:**
- Date
- Time
- Tank
- Reading
- Employee
- Shift
- Remarks

---

## 14. FUEL RECONCILIATION

**Formula:**
```
Expected Closing Stock = Opening Stock + Fuel Received - Fuel Sold
```

**Compare:**
- Expected Stock vs Physical Stock

**Calculate:**
- Variance

**Do NOT automatically assume variance means theft.**

**Classify variances as:**
- NORMAL
- WARNING
- INVESTIGATION REQUIRED
- APPROVAL REQUIRED

**Thresholds must be configurable.**

---

## 15. DISPENSERS & NOZZLES

**Model:**
- Dispenser
- Nozzle
- Fuel Type
- Meter Reading
- Nozzle Assignment
- Nozzle Status

**Track:**
- Opening reading
- Closing reading
- Totalized reading
- Sales
- Attendant
- Shift
- Date

---

## 16. SALES

**Each sale must track:**
- Sale ID
- Date
- Time
- Shift
- Attendant
- Nozzle
- Fuel type
- Quantity
- Rate
- Amount
- Payment method
- Receipt number
- Customer where applicable

**Support:**
- Cash
- UPI
- Card
- Credit

**Prevention rules:**
- Prevent duplicate sales
- Completed sales should not be deleted
- Use cancellation/reversal mechanisms

---

## 17. PAYMENTS

**Track separately:**
- CASH
- UPI
- CARD
- CREDIT

**Payment states:**
- SUCCESS
- PENDING
- FAILED
- REVERSED
- REFUNDED

**Store:**
- Payment ID
- Sale ID
- Amount
- Method
- Reference number
- Date
- Time
- Attendant
- Shift

---

## 18. CREDIT CUSTOMERS

**Implement:**
- Customer
- Credit Account
- Credit Limit
- Credit Sale
- Invoice
- Customer Payment
- Outstanding
- Ledger

**Support:**
- Credit limits
- Due dates
- Partial payments
- Outstanding
- Overdue
- Credit blocking
- Statements

---

## 19. CASH MANAGEMENT

**Every attendant is accountable for their shift collection.**

**Track:**
- Expected cash
- Actual cash
- Variance

**Example:**
```
Expected:  ₹1,50,000
Actual:   ₹1,47,500
Variance: -₹2,500
```

**The system should create an exception.**

**Do NOT overwrite the original figures.**

---

## 20. RECONCILIATION

**Support the following reconciliation types:**
- Cash reconciliation
- UPI reconciliation
- Card reconciliation
- Fuel reconciliation
- Expense reconciliation
- Shift reconciliation

**Per category:**
- Attendant
- Nozzle
- Shift
- Date
- Fuel type

---

## 21. DISCREPANCY WORKFLOW

**Use the following workflow:**

1. Difference detected
2. Exception created
3. Supervisor review
4. Manager investigation
5. Explanation
6. Owner approval where required
7. Adjustment
8. Audit log

**Never silently change financial data.**

---

## 22. EXPENSE MANAGEMENT

**Track the following:**
- Expense category
- Amount
- Date
- Employee
- Shift
- Payment method
- Receipt
- Description
- Approval
- Status

**Support printing of expense reports.**

---

## 23. DATABASE

**Use SQLite.**

**Use UUID primary keys.**

**Use foreign keys.**

**Use indexes.**

**Use constraints.**

**Use transactions.**

**Use normalization.**

**Core tables:**
- users
- roles
- permissions
- employees
- attendance
- leave
- shifts
- shift_assignments
- dispensers
- nozzles
- nozzle_assignments
- fuel_types
- tanks
- tank_readings
- inventory_transactions
- suppliers
- purchase_orders
- purchase_order_items
- fuel_deliveries
- supplier_invoices
- supplier_payments
- customers
- credit_accounts
- credit_sales
- customer_payments
- sales
- sale_items
- payments
- expenses
- expense_categories
- reconciliations
- reconciliation_items
- notifications
- audit_logs
- backups
- system_settings
- reports

---

## 24. DATABASE SAFETY

- Enable SQLite foreign keys.
- Use WAL mode where appropriate.
- Use transactions.
- Do not allow partial financial writes.
- Implement database integrity checks.
- Implement backup before migrations.
- Implement restore testing.

---

## 25. REPORTING SYSTEM

**This is a CORE REQUIREMENT.**

The desktop application must provide comprehensive reports.

Reports should be available by:
- Day
- Date range
- Shift
- Employee
- Attendant
- Nozzle
- Fuel type
- Payment method
- Customer
- Supplier

---

## 26. DAILY REPORTS

Implement the following daily reports:
- Daily Sales Report
- Daily Fuel Sales Report
- Daily Payment Report
- Daily Cash Report
- Daily UPI Report
- Daily Card Report
- Daily Credit Report
- Daily Expense Report
- Daily Inventory Report
- Daily Reconciliation Report
- Daily Attendant Report
- Daily Shift Report
- Daily Tank Report
- Daily Nozzle Report
- Daily Purchase Report

---

## 27. SHIFT REPORTS

Implement the following shift reports:
- Shift Summary
- Attendant-wise Sales
- Nozzle-wise Sales
- Fuel-wise Sales
- Payment-wise Sales
- Cash Reconciliation
- UPI Reconciliation
- Card Reconciliation
- Fuel Reconciliation
- Expense Summary
- Discrepancy Report
- Shift Closing Report

---

## 28. ATTENDANT REPORTS

Each attendant must have:
- Attendance Report
- Shift History
- Nozzle Assignment History
- Sales Report
- Fuel Volume
- Transaction Count
- Cash Collection
- UPI Collection
- Card Collection
- Credit Sales
- Reconciliation History
- Shortage/Excess History
- Performance Summary

---

## 29. HR REPORTS

Implement:
- Employee Master Report
- Attendance Report
- Late Arrival Report
- Absence Report
- Leave Report
- Shift Attendance Report
- Employee Performance Report
- Nozzle Assignment Report
- Employee Activity Report

---

## 30. INVENTORY REPORTS

Implement:
- Tank Stock Report
- Fuel Movement Report
- Opening/Closing Stock
- Fuel Purchase Report
- Fuel Sales Report
- Tank Variance Report
- Fuel Reconciliation Report
- Low Stock Report

---

## 31. FINANCIAL REPORTS

Implement:
- Cash Book
- Payment Summary
- Expense Summary
- Customer Outstanding
- Credit Sales
- Customer Ledger
- Supplier Ledger
- Supplier Outstanding
- Purchase Summary
- Daily Financial Summary
- Monthly Financial Summary
- Profitability-ready report

---

## 32. MANAGEMENT REPORTS

Implement:
- Management Dashboard
- Daily Business Summary
- Monthly Business Summary
- Sales Trends
- Fuel-wise Performance
- Attendant Performance
- Shift Performance
- Expense Trends
- Inventory Trends
- Outstanding Summary
- Exception Summary

---

## 33. PRINTING

**Every important report must support:**
- PRINT
- PRINT PREVIEW
- PDF EXPORT
- EXCEL EXPORT

**Where appropriate:**
- CSV EXPORT

**Reports should be formatted professionally.**

**Use ReportLab for PDF generation.**

**Use openpyxl for Excel reports.**

**Use Qt printing capabilities for direct printer output.**

---

## 34. PRINTABLE DOCUMENTS

Support printing:
- Sales receipts
- Shift reports
- Daily reports
- Cash reconciliation
- Fuel reconciliation
- Attendance reports
- Employee reports
- Purchase reports
- Supplier invoices
- Customer statements
- Supplier statements
- Expense reports
- Inventory reports
- Management summaries

---

## 35. REPORT FILTER SYSTEM

Every report should support appropriate filters:
- Date From
- Date To
- Shift
- Employee
- Attendant
- Nozzle
- Fuel Type
- Payment Method
- Customer
- Supplier
- Status
- Outlet (if multi-outlet architecture is retained)

**Users should be able to:**
- Generate
- Preview
- Print
- Export PDF
- Export Excel

---

## 36. DASHBOARD

The desktop dashboard should show:

- Today's Sales
- Today's Litres
- Cash
- UPI
- Card
- Credit
- Expenses
- Current Inventory
- Tank Levels
- Active Shift
- Attendant Count
- Present Employees
- Nozzle Assignments
- Reconciliation Status
- Outstanding
- Alerts

---

## 37. USER EXPERIENCE

The application is used in a petrol pump environment.

Therefore:
- Speed > visual complexity.
- Large readable numbers
- Simple navigation
- Minimal clicks
- Keyboard shortcuts
- Clear status indicators
- Fast data entry
- Confirmation for destructive actions
- Strong validation
- Search
- Filters
- Print buttons
- Export buttons
- Offline status indicator
- Current shift indicator
- Current user indicator

---

## 38. ATTENDANT UI

An attendant should see:
- My Shift
- My Nozzle
- Opening Meter
- Current Sales
- Payment Summary
- Attendance
- Closing Shift

**An attendant should NOT see:**
- Owner-level financial data
- Other employee confidential information
- System configuration
- Unauthorized reports

---

## 39. SECURITY

Implement:
- Username/password
- Strong password hashing
- RBAC
- Session management
- Auto logout
- Login attempt protection
- Permission checks
- Audit logging
- Database encryption strategy
- Backup encryption
- Sensitive-action confirmation

**Do not store plaintext passwords.**

---

## 40. AUDIT LOG

**Audit every event:**
- Login
- Logout
- Failed login
- Sale creation
- Sale cancellation
- Sale modification
- Expense creation
- Expense approval
- Inventory adjustment
- Tank reading correction
- Nozzle reassignment
- Shift reopening
- Reconciliation adjustment
- Employee modification
- Attendance correction
- Permission change
- System setting change
- Backup
- Restore

**Every audit record must contain:**
- Who
- What
- When
- Why
- Old value
- New value
- Device

---

## 41. BACKUP SYSTEM

Because there is NO CLOUD:

**Implement:**
- Automatic scheduled backups
- Manual backup
- Backup before database migration
- Backup before restore
- Backup verification
- Backup history
- Restore capability
- Backup location configuration

**Support:**
- Local disk
- External USB drive
- Network folder where available

**Do NOT assume cloud storage.**

---

## 42. DATABASE RECOVERY

**Implement:**
- Database integrity check.
- Backup verification.
- Restore workflow.
- Corrupted database detection.
- Recovery instructions.

**Never allow an administrator to accidentally overwrite the only valid backup.**

---

## 43. NOTIFICATIONS

**Create local application alerts for:**
- Low fuel
- Fuel variance
- Cash shortage
- Cash excess
- Payment mismatch
- Failed reconciliation
- Attendance issue
- Unauthorized action
- Pending approval
- Outstanding credit
- Supplier payment due
- Backup failure
- Database error

---

## 44. PERFORMANCE

The application must remain responsive during:
- High transaction volumes
- Large report generation
- Database backups
- Printing
- Excel export
- PDF generation

**Do heavy operations outside the main UI thread.**
**Never freeze the application while generating a large report.**

---

## 45. TESTING

**Use pytest.**

**Test the following:**
- Authentication
- RBAC
- Sales
- Payments
- Inventory
- Fuel reconciliation
- Cash reconciliation
- Shift closing
- Nozzle assignment
- Attendance
- HR
- Reports
- Printing
- Backup
- Restore
- Database integrity
- Error handling
- Edge cases

---

## 46. IMPORTANT EDGE CASES

**Test the following scenarios:**
- Internet unavailable
- Computer restart during transaction
- Application crash during sale
- Duplicate sale
- Duplicate payment
- Wrong meter reading
- Negative inventory
- Wrong fuel type
- Attendant reassignment
- Nozzle reassignment
- Shift opened but not closed
- Cash shortage
- Cash excess
- Tank variance
- Cancelled sale
- Credit limit exceeded
- Partial payment
- Database corruption
- Backup failure
- Printer unavailable
- Printer out of paper
- Large report
- Invalid date
- Unauthorized adjustment

---

## 47. GIT & GITHUB

GitHub is the central project repository.

**Store:**
- Source code
- Documentation
- Architecture
- Database design
- ER diagrams
- Mermaid diagrams
- Requirements
- Testing documentation
- Decision records
- Roadmap
- Issues
- Changelog

**Never store:**
- Passwords
- API keys
- Database secrets
- Private credentials
- Real customer data
- Production backup files

---

## 48. PROJECT_CONTEXT.md

Maintain PROJECT_CONTEXT.md as the project's permanent memory.

It must contain:
- Project objective
- Business understanding
- Current architecture
- Technology stack
- Database design
- Completed modules
- Current module
- Pending modules
- Known bugs
- Known limitations
- Open questions
- Assumptions
- Architecture decisions
- Security decisions
- Testing status
- Backup status
- Deployment/package status
- Next task
- Future scope

---

## 49. CLAUDE.md

Create CLAUDE.md that instructs any AI coding agent to:

1. Read PROJECT_CONTEXT.md first.
2. Read architecture documents.
3. Inspect existing code.
4. Do not rewrite working code unnecessarily.
5. Do not invent business rules.
6. Ask/record assumptions.
7. Follow architecture.
8. Write tests.
9. Update documentation.
10. Update PROJECT_CONTEXT.md.
11. Never commit secrets.
12. Never modify database schema without migration.
13. Never remove historical financial data.

---

## 50. DOCUMENTATION

Create the following documentation files:
- 01-business-understanding.md
- 02-requirements.md
- 03-use-cases.md
- 04-system-architecture.md
- 05-database-design.md
- 06-api-and-service-design.md
- 07-security.md
- 08-offline-operation.md
- 09-hr-module.md
- 10-reconciliation.md
- 11-reporting.md
- 12-printing.md
- 13-backup-recovery.md
- 14-testing.md
- 15-user-manual.md
- 16-administration.md
- 17-future-scope.md

---

## 51. ARCHITECTURE DIAGRAMS

Create Mermaid diagrams for:
- System Architecture
- Database ER Diagram
- Business Workflow
- Shift Workflow
- Sales Workflow
- Fuel Procurement
- Fuel Reconciliation
- Cash Reconciliation
- Attendance Workflow
- Nozzle Assignment
- HR Workflow
- Backup Workflow
- Authentication
- RBAC
- Report Generation
- Printing
- Application Component Diagram
- Deployment Diagram

---

## 52. DEVELOPMENT PROCESS

**Do NOT build everything simultaneously.**

**Phase 1:**
- Business documentation

**Phase 2:**
- Architecture

**Phase 3:**
- Database

**Phase 4:**
- Authentication/RBAC

**Phase 5:**
- Employees/HR

**Phase 6:**
- Attendance

**Phase 7:**
- Shifts

**Phase 8:**
- Nozzles

**Phase 9:**
- Tanks/Inventory

**Phase 10:**
- Procurement

**Phase 11:**
- Sales

**Phase 12:**
- Payments

**Phase 13:**
- Credit

**Phase 14:**
- Expenses

**Phase 15:**
- Reconciliation

**Phase 16:**
- Reports

**Phase 17:**
- Printing

**Phase 18:**
- Backup/Restore

**Phase 19:**
- Testing

**Phase 20:**
- Packaging

**Phase 21:**
- Pilot deployment

---

## 53. FEATURE DEFINITION OF DONE

A feature is complete only when:
- Business logic
- Database
- UI
- Validation
- Permissions
- Audit
- Error handling
- Tests
- Documentation
- Report integration where applicable
- Backup implications
- PROJECT_CONTEXT update
- Git commit
- GitHub issue update

Are all completed.

---

## 54. GIT BRANCHING

Use:
- main
- develop
- feature/*
- bugfix/*
- hotfix/*

**Workflow:**
1. Issue
   ↓
2. Feature branch
   ↓
3. Implementation
   ↓
4. Tests
   ↓
5. Documentation
   ↓
6. Pull Request
   ↓
7. Review
   ↓
8. CI
   ↓
9. Merge

---

## 55. COMMIT CONVENTION

Use:
- **feat:** - Add new feature
- **fix:** - Fix bug
- **docs:** - Documentation
- **refactor:** - Code refactoring
- **test:** - Add tests
- **chore:** - Chore/Build
- **security:** - Security changes
- **perf:** - Performance improvements

**Examples:**
- feat: add daily nozzle assignment
- feat: implement attendant attendance
- feat: add fuel reconciliation
- feat: add printable shift report
- fix: prevent duplicate sales
- docs: document cash reconciliation
- test: add nozzle assignment tests

---

## 56. RELEASE

Package the desktop application using PyInstaller.

**Provide:**
- Windows executable
- Installer
- Configuration system
- Database initialization
- Backup directory
- Logs directory
- Reports directory
- User documentation
- Administrator documentation
- Recovery documentation

---

## 57. FUTURE-PROOFING

Although there is NO cloud requirement now, do not create architecture that makes future expansion impossible.

**Keep business logic separated from UI.**
**Keep repositories separated.**
**Keep domain models clean.**
**Use UUIDs.**
**Use proper audit trails.**
**Keep database relationships normalized.**

**Future possibilities (do NOT implement now):**
- Web application
- Cloud synchronization
- Mobile application
- IoT tank sensors
- Dispenser integration
- AI forecasting
- Fraud detection
- Biometric attendance
- CCTV
- WhatsApp reports
- GST automation

---

## 58. CRITICAL BUSINESS PRINCIPLE

**The system must never silently change historical financial data.**

**Instead of:**
- DELETE
- OVERWRITE

**Use:**
- VOID
- REVERSE
- ADJUST
- APPROVE
- AUDIT

**This applies to:**
- Sales
- Payments
- Expenses
- Inventory
- Reconciliation
- Credit
- Supplier transactions

---

## 59. FINAL ARCHITECTURE

The final system should conceptually be:

```
                      ┌─────────────────────────┐
                      │     PETROL PUMP STAFF   │
                      └────────────┬────────────┘
                                   │
                                   ▼
                      ┌─────────────────────────┐
                      │      PYTHON DESKTOP      │
                      │         PySide6          │
                      ├─────────────────────────┤
                      │ Sales                    │
                      │ Inventory                │
                      │ Procurement              │
                      │ Payments                 │
                      │ Reconciliation           │
                      │ HR                       │
                      │ Attendance               │
                      │ Shifts                   │
                      │ Nozzle Assignment        │
                      │ Reports                  │
                      │ Printing                 │
                      │ Backup                   │
                      └────────────┬────────────┘
                                   │
                                   ▼
                      ┌─────────────────────────┐
                      │       SERVICE LAYER      │
                      ├─────────────────────────┤
                      │ Business Rules           │
                      │ Validation               │
                      │ Permissions              │
                      │ Reconciliation           │
                      │ Reporting               │
                      └────────────┬────────────┘
                                   │
                                   ▼
                      ┌─────────────────────────┐
                      │      REPOSITORIES        │
                      └────────────┬────────────┘
                                   │
                                   ▼
                      ┌─────────────────────────┐
                      │       SQLAlchemy         │
                      └────────────┬────────────┘
                                   │
                                   ▼
                      ┌─────────────────────────┐
                      │         SQLite           │
                      │       LOCAL ONLY         │
                      └────────────┬────────────┘
                                   │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
         BACKUPS           REPORTS           PRINTING
              │                 │                 │
              ▼                 ▼                 ▼
         USB/DISK          PDF/Excel          PRINTER
```

---

## 60. FIRST TASK

**DO NOT IMPLEMENT BUSINESS FEATURES YET.**

**First:**

1. Create repository
2. Create folder structure
3. Create PROJECT_CONTEXT.md
4. Create CLAUDE.md
5. Create README.md
6. Create architecture documentation
7. Create database ER diagram
8. Create business workflow
9. Create RBAC matrix
10. Create requirements
11. Create development roadmap
12. Create initial ADRs
13. Initialize Git
14. Create initial commit
15. Prepare GitHub repository structure

**Then stop and review the architecture before beginning implementation.**

**The goal is not to produce the maximum amount of code.**

**The goal is to build a reliable, maintainable, offline-first petrol-pump ERP that can actually be used in a real petrol pump.**

**Always prioritize:**
- BUSINESS CORRECTNESS
- DATA INTEGRITY
- SECURITY
- RELIABILITY
- USABILITY
- MAINTAINABILITY
- PERFORMANCE
- FEATURE COUNT

**Begin with requirements and architecture discovery.**

---

*This problem statement defines the complete requirements for the Petrol Pump Management ERP. The following sections provide detailed architecture, database design, and implementation guidance.*
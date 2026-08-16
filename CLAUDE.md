# Petrol Pump ERP - Development Guidelines

## Read First
Always read PROJECT_CONTEXT.md before starting any implementation task.

## Architecture
- Follow the modular architecture defined in the project
- Do NOT put business logic directly inside UI widgets
- Do NOT put SQL queries everywhere
- Use repositories and services
- Use SQLAlchemy 2.x with SQLite

## Technology Stack
- Python 3.13+
- PySide6 for UI
- SQLite database
- SQLAlchemy 2.x ORM
- Alembic for migrations
- Pydantic for validation
- pytest for testing
- ReportLab for PDF
- openpyxl for Excel
- pydantic-settings for configuration
- Python logging for logging
- PyInstaller for packaging

## Database Rules
- Always use UUID primary keys
- Always use foreign keys
- Use WAL mode where appropriate
- Always use transactions for financial operations
- Never allow partial financial writes
- Implement database integrity checks
- Implement backup before migrations
- Never remove historical financial data
- Implement restore testing

## Development Rules
- Always follow the architecture defined in ARCHITECTURE.md
- Never rewrite working code unnecessarily
- Do not invent business rules - follow existing patterns
- Ask/record assumptions before implementing
- Write tests for all new features
- Update PROJECT_CONTEXT.md after each session
- Update CLAUDE.md if architecture changes

## Git Rules
- Never commit secrets (passwords, API keys, database secrets)
- Never modify database schema without migration
- Never remove historical financial data
- Use proper commit conventions (feat:, fix:, docs:, etc.)
- Always create feature branches for new features
- Always add tests before merging

## Reporting Rules
- All important reports must support: PRINT, PRINT PREVIEW, PDF EXPORT, EXCEL EXPORT
- Users should be able to: Generate, Preview, Print, Export PDF, Export Excel
- Every report should support appropriate filters (date range, employee, nozzle, etc.)

## Security Rules
- Do not store plaintext passwords
- Implement strong password hashing
- Implement RBAC
- Implement session management with auto logout
- Implement permission checks
- Implement audit logging for all changes

## Testing Rules
- Use pytest for all testing
- Test authentication, RBAC, sales, payments, inventory, fuel reconciliation, cash reconciliation, shift closing, nozzle assignment, attendance, HR, reports, printing, backup, restore, database integrity, error handling, edge cases
- Never remove historical financial data

## Offline Rules
- Application must work entirely offline
- No web application framework
- No remote monitoring
- No cloud database
- No online synchronization

## Important
- Always prioritize: BUSINESS CORRECTNESS > DATA INTEGRITY > SECURITY > RELIABILITY > USABILITY > MAINTAINABILITY > PERFORMANCE > FEATURE COUNT
- Always prioritize: The system must never silently change historical financial data. Instead of DELETE or OVERWRITE use: VOID, REVERSE, ADJUST, APPROVE, AUDIT
- Begin with requirements and architecture discovery
- Begin with business documentation before code
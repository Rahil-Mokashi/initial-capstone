# Petrol Pump ERP

A complete offline-first Petrol Pump Management ERP built with Python and PySide6.

## Overview

This is a desktop application designed to run on a petrol pump computer and operate reliably even when there is NO INTERNET CONNECTION. It manages all aspects of petrol pump operations including fuel inventory, sales, procurement, HR, reporting, and more.

## Features

- **Fuel Inventory Management**: Track fuel deliveries, tank levels, and stock reconciliation
- **Sales Management**: Handle fuel dispensing, product sales, and payment processing
- **Procurement**: Manage supplier orders, fuel deliveries, and supplier payments
- **Shift Management**: Open/close shifts with complete reconciliation
- **Employee Management**: Attendance, shifts, nozzle assignments, performance
- **Reporting**: Comprehensive reports with PDF/Excel export
- **Printing**: Professional reports and receipts
- **Backup/Restore**: Automated and manual backup with verification
- **Audit Trail**: Complete audit logging for all changes
- **RBAC**: Role-based access control

## Technology Stack

- **Frontend**: PySide6 (Qt for Python)
- **Database**: SQLite (single file, zero-config)
- **ORM**: SQLAlchemy 2.x
- **Migrations**: Alembic
- **Validation**: Pydantic
- **Testing**: pytest
- **Reports**: ReportLab (PDF), openpyxl (Excel)
- **Configuration**: pydantic-settings
- **Logging**: Python standard logging
- **Packaging**: PyInstaller

## Project Structure

```
petrol-pump-erp/
├── app/
│   ├── main.py
│   ├── core/
│   │   ├── config.py
│   │   ├── security.py
│   │   ├── logging.py
│   │   ├── exceptions.py
│   │   └── constants.py
│   ├── database/
│   │   ├── connection.py
│   │   ├── session.py
│   │   ├── base.py
│   │   └── migrations/
│   ├── models/
│   ├── repositories/
│   ├── services/
│   ├── schemas/
│   ├── ui/
│   │   ├── windows/
│   │   ├── dialogs/
│   │   ├── widgets/
│   │   └── components/
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
│   └── utils/
├── tests/
├── docs/
├── scripts/
├── backups/
├── reports/
├── .github/
├── README.md
├── PROJECT_CONTEXT.md
├── CLAUDE.md
├── ARCHITECTURE.md
├── ROADMAP.md
├── CHANGELOG.md
├── CONTRIBUTING.md
└── SECURITY.md
```

## Quick Start

```bash
# Clone the repository
git clone https://github.com/your-org/petrol-pump-erp.git
cd petrol-pump-erp

# Create virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python -m app.main
```

> If PySide6 is installed, the application launches the desktop UI. Otherwise the app starts in CLI fallback mode and prints initialization status.

## Requirements

- Python 3.13+
- PySide6
- SQLAlchemy 2.x
- See requirements.txt for full list

## Documentation

- [Architecture](ARCHITECTURE.md)
- [Roadmap](ROADMAP.md)
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)

## License

Proprietary - All rights reserved
"""One-off verification script for the 2026-09-16 navigation restructure
and alert strip (Part C: "Verify with real screenshots as a broadly-
permissioned role and a restricted role, and specifically render the
alert strip with several real seeded alert types").

Runs against an ISOLATED temporary SQLite database (never the real
dev/production petrol_pump.db - the same tmp_path pattern the test suite
uses) so this can be run freely without touching real data.

Seeds directly via the ORM/service layer rather than
scripts/seed_demo_data.py: that script currently raises
(ShiftReconciliation no longer has the cash/upi/card columns it still
constructs - it was not updated for the "columns become rows" per-tender
migration, see PROJECT_CONTEXT.md). That is a pre-existing, unrelated
bug, out of scope for this navigation/alerts pass to fix - this script
works around it by seeding only what it actually needs directly (a low
tank, a pending expense, an attendant login), rather than the full
70-day demo dataset.

Not a pytest test and not part of CI - purely a manual verification aid.

Run with: python scripts/verify_navigation_and_alerts.py
"""

import sys
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

qapp = QApplication.instance() or QApplication([])

import app.database.connection as db_connection

TMP_DIR = Path(tempfile.mkdtemp(prefix="petrolpump_verify_"))
DB_PATH = TMP_DIR / "verify.db"
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
db_connection.engine = engine
db_connection.SessionLocal = session_factory
db_connection.DB_PATH = str(DB_PATH)

import app.models  # noqa: E402,F401 (registers all table metadata)
from app.core.security import hash_password  # noqa: E402
from app.database.connection import init_db  # noqa: E402
from app.database.seed import seed_initial_data  # noqa: E402
from app.models.employee import Employee  # noqa: E402
from app.models.expense import Expense, ExpenseCategory  # noqa: E402
from app.models.fuel import Fuel  # noqa: E402
from app.models.role import Role  # noqa: E402
from app.models.tank import Tank  # noqa: E402
from app.models.user import User  # noqa: E402

init_db()
seed_initial_data()

session = session_factory()
try:
    admin = session.query(User).filter_by(username="admin").first()
    attendant_role = session.query(Role).filter_by(name="attendant").first()

    # A restricted-role login, for the "restricted role" screenshot pass.
    attendant_user = User(
        username="attendant1", email="attendant1@example.com",
        password_hash=hash_password("Passw0rd!"), role=attendant_role, is_active=True,
    )
    session.add(attendant_user)
    session.commit()
    attendant_employee = Employee(
        employee_code="EMP-1001", first_name="Ravi", last_name="Kumar",
        contact_number="9876543210", joining_date=date.today(), designation="Attendant",
        user_id=attendant_user.id,
    )
    session.add(attendant_employee)
    session.commit()

    # A real LOW_FUEL alert: a tank well under the reorder threshold.
    fuel = session.query(Fuel).filter_by(fuel_type="Petrol").first()
    session.add(Tank(
        code="TANK-LOW", fuel_id=fuel.id, capacity=Decimal("10000"),
        current_stock=Decimal("350"), opening_stock=Decimal("350"), status="active",
    ))

    # A real PENDING_APPROVAL alert: an expense awaiting sign-off.
    category = ExpenseCategory(name="Maintenance", status="active")
    session.add(category)
    session.commit()
    session.add(Expense(
        expense_date=date.today(), category_id=category.id, amount=Decimal("4500.00"),
        payment_method="cash", description="Compressor repair", status="pending",
        employee_id=attendant_employee.id, recorded_by_id=admin.id,
    ))

    session.commit()
    # BACKUP_FAILURE fires on its own here: a fresh database with no
    # backups ever taken is exactly the condition that alert reports.
finally:
    session.close()

from app.ui.main_window import AppController  # noqa: E402

OUT_DIR = ROOT / "docs" / "screenshots" / "verify-2026-09-16"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def grab(widget, name: str, size=(1440, 900)) -> None:
    widget.resize(*size)
    widget.show()
    for _ in range(8):
        qapp.processEvents()
    pixmap = widget.grab()
    pixmap.save(str(OUT_DIR / name))
    widget.hide()
    print(f"Saved {name} ({pixmap.width()}x{pixmap.height()})")


def capture_role(username: str, password: str, label: str) -> None:
    from PySide6.QtWidgets import QDialog

    controller = AppController()
    success, user_data, error = controller._auth_service.authenticate(
        username, password, device_info="verification-capture"
    )
    if not success:
        raise SystemExit(f"Could not log in as {username} for capture: {error}")

    # admin always starts with must_change_password=True (see seed.py) -
    # _show_main_window would otherwise construct a real, forced,
    # blocking ChangePasswordDialog here. Same fix as
    # tests/test_main_window_open_paths.py's main_window fixture.
    original_exec = QDialog.exec
    QDialog.exec = lambda self: QDialog.Accepted
    try:
        controller._show_main_window(user_data)
    finally:
        QDialog.exec = original_exec
    window = controller.main_window

    # Let refresh_alert_badge's deferred fetch happen for real: the
    # session timer normally does this ~60s after login (see its own
    # comment on why it cannot happen synchronously at construction
    # time), but a one-off script does not need to wait a real minute
    # for it - calling it directly here is exactly the same call the
    # timer makes, just triggered immediately instead of on a delay.
    window.refresh_alert_badge()
    for _ in range(5):
        qapp.processEvents()

    grab(window, f"{label}-dashboard-with-alert-strip.png")

    window._open_masters_landing()
    grab(window, f"{label}-masters-landing.png")

    window._open_operations_landing()
    grab(window, f"{label}-operations-landing.png")

    window._open_settings_landing()
    grab(window, f"{label}-settings-landing.png")

    window.close()


def main() -> None:
    capture_role("admin", "Admin@123", "admin")
    capture_role("attendant1", "Passw0rd!", "attendant")
    print(f"\nAll screenshots saved under: {OUT_DIR}")


if __name__ == "__main__":
    main()

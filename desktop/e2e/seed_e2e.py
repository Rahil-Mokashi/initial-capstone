"""Builds the throwaway database the Electron end-to-end tests run against.

Run from the repo root with PETROL_PUMP_DB_PATH pointing at a NEW file:
    python desktop/e2e/seed_e2e.py

Uses the real startup path (migrations + seed) so the schema is exactly what the app creates,
then adds a few users, an employee and two tanks. Never touches any other database.
"""

import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

if not os.environ.get("PETROL_PUMP_DB_PATH"):
    sys.exit("PETROL_PUMP_DB_PATH must be set - refusing to seed the default database.")

from app.core.constants import UserRole  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.database import connection  # noqa: E402
from app.database.seed import seed_initial_data  # noqa: E402
from app.models.employee import Employee  # noqa: E402
from app.models.fuel import Fuel  # noqa: E402
from app.models.role import Role  # noqa: E402
from app.models.tank import Tank  # noqa: E402
from app.models.user import User  # noqa: E402

PASSWORD = "Passw0rd!x"


def main() -> None:
    connection.init_db()
    seed_initial_data()
    session = connection.SessionLocal()
    try:
        for username, role in (
            ("admin1", UserRole.ADMIN),
            ("manager1", UserRole.MANAGER),
            ("accountant1", UserRole.ACCOUNTANT),
            ("attendant1", UserRole.ATTENDANT),
            ("owner1", UserRole.OWNER),
            ("dataentry1", UserRole.DATA_ENTRY),
        ):
            session.add(
                User(
                    username=username,
                    email=f"{username}@example.com",
                    password_hash=hash_password(PASSWORD),
                    first_name=username.title(),
                    last_name="Tester",
                    role=session.query(Role).filter_by(name=role.value).first(),
                    is_active=True,
                )
            )
        session.add(
            Employee(
                employee_code="EMP-0001", first_name="Ravi", last_name="Kumar",
                contact_number="9876543210", joining_date=date(2026, 1, 1),
            )
        )
        petrol = session.query(Fuel).filter_by(fuel_type="Petrol").first() or session.query(Fuel).first()
        diesel = session.query(Fuel).filter_by(fuel_type="Diesel").first() or petrol
        session.add(Tank(code="T1", fuel_id=petrol.id, capacity=Decimal("10000"),
                         current_stock=Decimal("2500.5"), opening_stock=Decimal("2500.5"), status="active"))
        session.add(Tank(code="T2", fuel_id=diesel.id, capacity=Decimal("10000"),
                         current_stock=Decimal("1800"), opening_stock=Decimal("1800"), status="active"))
        session.commit()
    finally:
        session.close()
    # Fold the WAL into the single file so the template can be copied as one file.
    with connection.engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    connection.engine.dispose()


if __name__ == "__main__":
    main()

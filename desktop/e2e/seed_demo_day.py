"""Builds a demo database of SYNTHETIC data for the documentation screenshots (never real figures).

Run from the repo root with PETROL_PUMP_DB_PATH pointing at a NEW file:
    python desktop/e2e/seed_demo_day.py

One pump day with the structure of the owner's report (tests/api/pump_day.py), credit customers of different ages with a
promise to chase, a bank statement imported and matched, and a payroll month, so every new screen has something to show.
"""

import base64
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "api"))

if not os.environ.get("PETROL_PUMP_DB_PATH"):
    sys.exit("PETROL_PUMP_DB_PATH must be set - refusing to seed the default database.")

from fastapi.testclient import TestClient  # noqa: E402

from api.app import create_app  # noqa: E402
from app.core.constants import UserRole  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.database import connection  # noqa: E402
from app.database.seed import seed_initial_data  # noqa: E402
from app.models.attendance import Attendance  # noqa: E402
from app.models.role import Role  # noqa: E402
from app.models.user import User  # noqa: E402
from api_helpers import SECRET, login  # noqa: E402
from pump_day import TODAY, build_day  # noqa: E402

PASSWORD = "Passw0rd!x"
T = date.today()


def main() -> None:
    connection.init_db()
    seed_initial_data()
    db = connection.SessionLocal()
    for username, role in (("admin1", UserRole.ADMIN), ("manager1", UserRole.MANAGER), ("accountant1", UserRole.ACCOUNTANT),
                           ("owner1", UserRole.OWNER), ("dataentry1", UserRole.DATA_ENTRY)):
        db.add(User(username=username, email=f"{username}@example.com", password_hash=hash_password(PASSWORD),
                    first_name=username.title(), last_name="Demo", role=db.query(Role).filter_by(name=role.value).first(), is_active=True))
    db.commit()

    app = create_app(SECRET, session_factory=connection.SessionLocal, session_timeout_hours=8)
    with TestClient(app, base_url="http://127.0.0.1", headers={"X-Launch-Secret": SECRET}) as client:
        manager, accountant, owner = login(client, "manager1"), login(client, "accountant1"), login(client, "owner1")
        day = build_day(client, manager, db)

        # credit customers of different ages, one promise to chase
        for name, ref, days, qty in (("Old Debtor Traders", "O1", 100, "20.000"), ("Newer Debtor Ltd", "N1", 45, "30.000")):
            c = client.post("/api/customers", headers=manager, json={"name": name}).json()
            client.post("/api/credit/accounts", headers=manager, json={"customer_id": c["id"], "credit_limit": "900000.00", "payment_due_days": 30})
            client.post("/api/bowser/bills", headers=manager, json={"bill_no": ref, "bill_date": (T - timedelta(days=days)).isoformat(), "customer_id": c["id"], "quantity": qty, "rate": "95.00", "transport": "200.00"})
            if ref == "N1":
                client.post(f"/api/credit/customers/{c['id']}/follow-ups", headers=accountant, json={"method": "call", "note": "says Friday", "promised_date": TODAY, "promised_amount": "1500.00"})

        # bank: payment apps settle into one account, cash into two
        wallet = client.post("/api/bank/accounts", headers=accountant, json={"name": "Wallet Bank", "account_mask": "XXXX1111", "modes": ["Paytm", "PhonePe", "DTP Card", "Card"]}).json()
        boi = client.post("/api/bank/accounts", headers=accountant, json={"name": "Bank of India", "account_mask": "XXXX1234", "modes": ["cash_deposit"]}).json()
        client.post("/api/bank/accounts", headers=accountant, json={"name": "Second Bank", "account_mask": "XXXX9876", "modes": ["cash_deposit"]})
        mapping = {"date_col": "Date", "description_col": "Narration", "debit_col": "Withdrawal", "credit_col": "Deposit", "balance_col": "Balance", "date_format": "%d/%m/%Y"}

        def statement(rows, opening):
            bal, out = opening, ["Date,Narration,Withdrawal,Deposit,Balance"]
            for text, credit in rows:
                bal += credit
                out.append(f"{T:%d/%m/%Y},{text},,{credit},{bal}")
            return "\n".join(out) + "\n"

        for acct, rows, opening in ((wallet, [("UPI PAYTM SETTLEMENT BATCH", 50000), ("PHONEPE SETTLEMENT", 5950), ("DTP FLEET CARD SETTLEMENT", 10000), ("TRUST DONATION RECEIVED", 777)], 100000),
                                    (boi, [("CASH DEPOSIT SELF", 50000)], 8000)):
            client.post(f"/api/bank/accounts/{acct['id']}/import", headers=accountant, json={"filename": "statement.csv", "content_base64": base64.b64encode(statement(rows, opening).encode()).decode(), "mapping": mapping})
        client.post("/api/bank/match/run", headers=accountant, json={"date_from": TODAY, "date_to": TODAY})

        # payroll for last month
        last_month_end = T.replace(day=1) - timedelta(days=1)
        for e in day["emps"][:2]:
            client.put(f"/api/payroll/salaries/{e}", headers=accountant, json={"monthly_salary": "24000.00", "effective_from": "2026-01-01"})
            for d in range(1, last_month_end.day + 1):
                db.add(Attendance(employee_id=e, attendance_date=last_month_end.replace(day=d), status="present" if d % 7 else "absent"))
        db.commit()
        client.post("/api/payroll/runs", headers=accountant, json={"month": f"{last_month_end:%Y-%m}"})
        client.post("/api/checks/run", headers=owner, json={"day": TODAY})
    db.close()
    with connection.engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    connection.engine.dispose()


if __name__ == "__main__":
    main()

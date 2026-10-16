"""Builds up to a year of SYNTHETIC pump data through the API (2 shifts a day, 12 nozzles, about 17,000 L a day, 10 credit bills a shift,
bowser bills, expenses, an oil sale, tank receipts, bank lines). Never real figures.

Usage (PETROL_PUMP_DB_PATH must point at a NEW file; it takes about 75 minutes for 365 days):
    python scripts/bench/generate_year.py 365
The automatic checks are switched off while loading, otherwise loading would take hours; scripts/bench/measure.py times them.
"""
import base64, json, os, random, sys, time
from datetime import date, timedelta
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests" / "api"))
if not os.environ.get("PETROL_PUMP_DB_PATH"):
    sys.exit("PETROL_PUMP_DB_PATH required")
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 365
PER_DISPENSER = int(os.environ.get("BENCH_NOZZLES_PER_DISPENSER", "2"))  # 2 = the old cap; 4 once the cap is a setting
OUT = Path(os.environ["PETROL_PUMP_DB_PATH"]).with_suffix(".meta.json")

from fastapi.testclient import TestClient  # noqa: E402
from api.app import create_app  # noqa: E402
from app.core.constants import UserRole  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.database import connection  # noqa: E402
from app.database.seed import seed_initial_data  # noqa: E402
from app.models.employee import Employee  # noqa: E402
from app.models.role import Role  # noqa: E402
from app.models.user import User  # noqa: E402
from api_helpers import SECRET, login  # noqa: E402

random.seed(7)
connection.init_db(); seed_initial_data()
db = connection.SessionLocal()
for u, r in (("manager1", UserRole.MANAGER), ("accountant1", UserRole.ACCOUNTANT), ("owner1", UserRole.OWNER), ("dataentry1", UserRole.DATA_ENTRY)):
    db.add(User(username=u, email=f"{u}@example.com", password_hash=hash_password("Passw0rd!x"), first_name=u.title(), last_name="Demo",
                role=db.query(Role).filter_by(name=r.value).first(), is_active=True))
db.commit()
import api.check_hook as _h  # bulk load only: the real hook re-runs checks after each write (measure.py times that)
(getattr(_h, "disable_for_bulk_load", None) or (lambda: setattr(_h.RunChecksAfterWrites, "_run", staticmethod(lambda request: None))))()
app = create_app(SECRET, session_factory=connection.SessionLocal, session_timeout_hours=8)
c = TestClient(app, base_url="http://127.0.0.1", headers={"X-Launch-Secret": SECRET}, raise_server_exceptions=True)
M, A, O, DE = login(c, "manager1"), login(c, "accountant1"), login(c, "owner1"), login(c, "dataentry1")


def post(h, path, body, ok=(200, 201)):
    r = c.post(path, headers=h, json=body)
    if r.status_code not in ok:
        raise SystemExit(f"POST {path} {r.status_code} {r.text[:300]}")
    return r.json()


def put(h, path, body):
    r = c.put(path, headers=h, json=body)
    if r.status_code != 200:
        raise SystemExit(f"PUT {path} {r.status_code} {r.text[:300]}")
    return r.json()


def timed(label, fn):
    t = time.perf_counter(); out = fn(); dt = time.perf_counter() - t
    return label, round(dt, 3), out


# ---- masters
fuels = {f["fuel_type"]: f["id"] for f in c.get("/api/lookups/fuels", headers=M).json()}
post(M, f"/api/fuel-prices/{fuels['Petrol']}/rate", {"new_rate_per_liter": "104.50"})
post(M, f"/api/fuel-prices/{fuels['Diesel']}/rate", {"new_rate_per_liter": "92.10"})
tank_defs = [("MS-22", "Petrol"), ("MS-16", "Petrol"), ("HSD-16", "Diesel"), ("HSD-22", "Diesel")]
tanks = {code: post(M, "/api/tanks", {"code": code, "fuel_id": fuels[f], "capacity": "200000", "opening_stock": "90000"}) for code, f in tank_defs}
nozzles = []
for d in range(1, 12 // PER_DISPENSER + 1):
    disp = post(M, "/api/dispensers", {"code": f"D{d}"})
    for k in range(PER_DISPENSER):
        n = (d - 1) * PER_DISPENSER + k + 1
        code, f = tank_defs[(n - 1) % 4]
        nozzles.append({"id": post(M, "/api/nozzles", {"code": f"N{n}", "dispenser_id": disp["id"], "fuel_id": fuels[f], "tank_id": tanks[code]["id"]})["id"], "tank": code, "meter": D("1000")})
emps = []
for n in range(1, 13):
    e = Employee(employee_code=f"E{n}", first_name=f"Staff{n}", last_name="T", contact_number="9000000000", joining_date=date(2025, 1, 1)); db.add(e); db.commit(); emps.append(e.id)
customers = []
for n in range(25):
    cu = post(M, "/api/customers", {"name": f"Customer {n:02d} Traders"})
    post(M, "/api/credit/accounts", {"customer_id": cu["id"], "credit_limit": "50000000.00", "payment_due_days": 30}); customers.append(cu["id"])
cat = post(M, "/api/expense-categories", {"name": "Tea"})
lube = post(M, "/api/lubricants", {"name": "HP Racer 1L", "pack_size": "1 ltr", "default_rate": "250.00"})
post(M, f"/api/lubricants/{lube['id']}/movements", {"kind": "opening", "quantity": "5000", "movement_date": "2020-01-01"})
post(M, "/api/bowser/opening", {"day": (date.today() - timedelta(days=DAYS + 1)).isoformat(), "litres": "20000.000", "rupees": "1800000.00", "reason": "synthetic"})
wallet = post(A, "/api/bank/accounts", {"name": "Wallet Bank", "account_mask": "XXXX1111", "modes": ["Paytm", "PhonePe", "DTP Card", "Card"]})
boi = post(A, "/api/bank/accounts", {"name": "Bank of India", "account_mask": "XXXX1234", "modes": ["cash_deposit"]})
MAP = {"date_col": "Date", "description_col": "Narration", "debit_col": "Withdrawal", "credit_col": "Deposit", "balance_col": "Balance", "date_format": "%d/%m/%Y"}
bank_rows = {"w": [], "b": []}
bank_bal = {"w": D("100000.00"), "b": D("100000.00")}
bank_open = {"w": D("100000.00"), "b": D("100000.00")}
bowser_meter = D("1000")
results = {"checkpoints": [], "gen_secs_per_day": []}
first = date.today() - timedelta(days=DAYS)
tid = {m["name"]: m["tender_id"] for m in c.get(f"/api/shift-totals/{post(M, '/api/shifts', {'shift_date': (first - timedelta(days=1)).isoformat(), 'shift_label': 'Seed'})['id']}", headers=M).json()}


def flush_bank(upto_day_label):
    for k, acct in (("w", wallet), ("b", boi)):
        if not bank_rows[k]:
            continue
        lines = ["Date,Narration,Withdrawal,Deposit,Balance"]; bal = bank_open[k]
        for when, text, credit in bank_rows[k]:
            bal += credit
            lines.append(f"{when:%d/%m/%Y},{text},,{credit},{bal}")
        text = "\n".join(lines) + "\n"
        r = c.post(f"/api/bank/accounts/{acct['id']}/import", headers=A, json={"filename": f"{k}-{upto_day_label}.csv", "content_base64": base64.b64encode(text.encode()).decode(), "mapping": MAP})
        if r.status_code != 201:
            raise SystemExit(f"import {r.status_code} {r.text[:300]}")
        bank_open[k] = bal; bank_rows[k] = []


t_all = time.perf_counter()
for i in range(1, DAYS + 1):
    d = first + timedelta(days=i - 1); t_day = time.perf_counter()
    shifts = [post(M, "/api/shifts", {"shift_date": d.isoformat(), "shift_label": lab}) for lab in ("Morning", "Evening")]
    if i % 4 == 1:  # a tanker for each tank every four days
        for code in tanks:
            post(M, f"/api/tanks/{tanks[code]['id']}/transactions", {"transaction_type": "receipt", "quantity": "17000", "reference": f"INV-{i}-{code}"})
    day_tot = {"Paytm": D(0), "PhonePe": D(0), "DTP Card": D(0)}; cash_dep = D(0)
    for si, sh in enumerate(shifts):
        aids = []
        for k, nz in enumerate(nozzles):
            r = post(M, f"/api/shifts/{sh['id']}/assignments", {"employee_id": emps[k], "nozzle_id": nz["id"], "opening_meter": str(nz["meter"])})
            aids.append(r["id"])
        credit_by_noz = {}
        for _ in range(10):
            k = random.randrange(12); q = D(random.randint(20, 150))
            post(M, "/api/sales", {"shift_id": sh["id"], "nozzle_id": nozzles[k]["id"], "employee_id": emps[k], "quantity": f"{q}.000", "payment_method": "credit", "customer_id": random.choice(customers)})
            credit_by_noz[k] = credit_by_noz.get(k, D(0)) + q
        litres = D(0)
        for k, nz in enumerate(nozzles):
            sold = D(random.randint(520, 900)) + credit_by_noz.get(k, D(0)) * D("0.0")
            sold = max(sold, credit_by_noz.get(k, D(0)) + 10); litres += sold
            closing = nz["meter"] + sold + D(5)
            post(M, f"/api/shift-assignments/{aids[k]}/complete", {"closing_meter": f"{closing}", "testing_volume": "5.000"}, (200, 201))
            nz["meter"] = closing
        for name, share in (("DTP Card", D("0.15")), ("PhonePe", D("0.12")), ("Paytm", D("0.25"))):
            amt = (litres * D("98") * share).quantize(D("0.01")); day_tot[name] += amt
            put(M, f"/api/shift-totals/{sh['id']}/{tid[name]}", {"amount": str(amt), "reference": "slip"})
        adv = (litres * D("98") * D("0.2")).quantize(D("0.01")); fin = (litres * D("98") * D("0.1")).quantize(D("0.01"))
        post(M, "/api/cash-book/movements", {"shift_id": sh["id"], "advance_amount": str(adv), "final_amount": str(fin)})
        dep = (adv + fin).quantize(D("1")); cash_dep += dep
        post(M, "/api/cash-book/deposits", {"shift_id": sh["id"], "bank_name": "Bank of India", "amount": str(dep)})
        for _ in range(2):
            post(M, "/api/expenses", {"category_id": cat["id"], "amount": "150.00", "payment_method": "cash", "employee_id": emps[0], "shift_id": sh["id"], "description": "Tea"})
        post(M, f"/api/lubricants/{lube['id']}/movements", {"kind": "sale", "quantity": "2", "shift_id": sh["id"], "customer_name": "Walk-in"})
    post(M, "/api/bowser/transfers", {"shift_id": shifts[0]["id"], "nozzle_id": nozzles[2]["id"], "employee_id": emps[2], "litres": "200.000"})
    for b in range(4):
        post(M, "/api/bowser/bills", {"bill_no": f"B{i}-{b}", "bill_date": d.isoformat(), "customer_id": random.choice(customers), "quantity": "50.000", "rate": "95.00", "transport": "250.00", "vehicle_no": "MH14XX0001", "slip_no": f"S{b}"})
    post(M, "/api/bowser/meter", {"day": d.isoformat(), "start_reading": str(bowser_meter), "testing": "0", "end_reading": str(bowser_meter + 200)}); bowser_meter += 200
    for sh in shifts:
        post(M, f"/api/shifts/{sh['id']}/close", {})
    for name, text in (("Paytm", "UPI PAYTM SETTLEMENT BATCH"), ("PhonePe", "PHONEPE SETTLEMENT"), ("DTP Card", "DTP FLEET CARD SETTLEMENT")):
        bank_rows["w"].append((d, text, day_tot[name]))
    bank_rows["b"].append((d, "CASH DEPOSIT", cash_dep))
    results["gen_secs_per_day"].append(round(time.perf_counter() - t_day, 2))
    if i % 15 == 0:
        print(f"day {i}/{DAYS} {time.perf_counter() - t_all:.0f}s last day {results['gen_secs_per_day'][-1]}s", flush=True)
flush_bank(DAYS)
OUT.write_text(json.dumps({"days": DAYS, "first_day": first.isoformat(), "last_day": d.isoformat(), "gen_secs_per_day": results["gen_secs_per_day"]}))
print("DONE", round(time.perf_counter() - t_all), "s", flush=True)




"""A synthetic pump day with the SAME structure as the owner's daily report (no real names or figures).

Four tanks named like the report's columns (MS-22, MS-16, HSD-16, HSD-22), two shifts, credit bills,
card/phone-app totals, a cash book with two bank deposits, expenses (one internal fuel use), two
lubricants, and the bowser (stock transfer, two bills, meter). Every number is chosen so the
expected report figures are easy to check by hand; see EXPECTED at the bottom.

Prices: petrol 100.00/L, diesel 90.00/L.
"""

from datetime import date
from decimal import Decimal

from app.models.employee import Employee

TODAY = date.today().isoformat()


def _post(client, h, path, body, status=201):
    r = client.post(path, headers=h, json=body)
    assert r.status_code == status, (path, r.status_code, r.text)
    return r.json()


def _employee(db, n):
    e = Employee(
        employee_code=f"E{n}", first_name=f"Staff{n}", last_name="Tester", contact_number="9000000000",
        joining_date=date(2026, 1, 1),
    )
    db.add(e)
    db.commit()
    return e.id


def build_day(client, h, db):
    """Creates the whole day through the API as `h` (a manager). Returns ids the tests need."""
    fuels = {f["fuel_type"]: f["id"] for f in client.get("/api/lookups/fuels", headers=h).json()}
    _post(client, h, f"/api/fuel-prices/{fuels['Petrol']}/rate", {"new_rate_per_liter": "100.00"}, 200)
    _post(client, h, f"/api/fuel-prices/{fuels['Diesel']}/rate", {"new_rate_per_liter": "90.00"}, 200)

    tank_defs = [("MS-22", "Petrol", "35485"), ("MS-16", "Petrol", "12000"), ("HSD-16", "Diesel", "8000"), ("HSD-22", "Diesel", "20000")]
    tanks = {}
    for code, fuel, stock in tank_defs:
        tanks[code] = _post(client, h, "/api/tanks", {"code": code, "fuel_id": fuels[fuel], "capacity": "100000", "opening_stock": stock})
    # The app caps a dispenser at two nozzles (MAX_NOZZLES_PER_DISPENSER); the site notes say 4 per dispenser,
    # logged as NEEDS HUMAN REVIEW. Two dispensers here.
    dispensers = [_post(client, h, "/api/dispensers", {"code": f"D{n}"}) for n in (1, 2)]
    nozzles = {}
    for i, (code, fuel, _) in enumerate(tank_defs, start=1):
        d = dispensers[(i - 1) // 2]
        nozzles[code] = _post(client, h, "/api/nozzles", {"code": f"N{i}", "dispenser_id": d["id"], "fuel_id": fuels[fuel], "tank_id": tanks[code]["id"]})

    # purchase of 23,000 L into MS-22 during the day
    _post(client, h, f"/api/tanks/{tanks['MS-22']['id']}/transactions", {"transaction_type": "receipt", "quantity": "23000", "reference": "Invoice 1"})

    emps = [_employee(db, n) for n in range(1, 5)]
    s1 = _post(client, h, "/api/shifts", {"shift_date": TODAY, "shift_label": "Morning"})
    s2 = _post(client, h, "/api/shifts", {"shift_date": TODAY, "shift_label": "Evening"})

    acme = _post(client, h, "/api/customers", {"name": "ACME Traders"})
    beta = _post(client, h, "/api/customers", {"name": "Beta Concrete"})
    for c in (acme, beta):
        _post(client, h, "/api/credit/accounts", {"customer_id": c["id"], "credit_limit": "500000.00", "payment_due_days": 30})

    def assign(shift, code, emp, opening):
        r = _post(client, h, f"/api/shifts/{shift['id']}/assignments", {"employee_id": emp, "nozzle_id": nozzles[code]["id"], "opening_meter": opening})
        return r["id"]

    def sale(shift, code, emp, qty, method="cash", customer=None):
        body = {"shift_id": shift["id"], "nozzle_id": nozzles[code]["id"], "employee_id": emp, "quantity": qty, "payment_method": method}
        if customer:
            body["customer_id"] = customer["id"]
        return _post(client, h, "/api/sales", body)

    def complete(aid, closing, testing="0"):
        _post(client, h, f"/api/shift-assignments/{aid}/complete", {"closing_meter": closing, "testing_volume": testing}, 200)

    # ---- Shift 1: MS-22 995 L (20 L on credit), HSD-16 500 L (200 L is the Stock Transfer to the bowser)
    a1 = assign(s1, "MS-22", emps[0], "0")
    a3 = assign(s1, "HSD-16", emps[2], "0")
    credit1 = sale(s1, "MS-22", emps[0], "20.000", "credit", acme)
    transfer = _post(client, h, "/api/bowser/transfers", {"shift_id": s1["id"], "nozzle_id": nozzles["HSD-16"]["id"], "employee_id": emps[2], "litres": "200.000"})
    complete(a1, "1000.000", "5.000")
    complete(a3, "500.000")

    # ---- Shift 2: MS-22 500 L, HSD-16 400 L (100 L on credit)
    b1 = assign(s2, "MS-22", emps[0], "1000.000")
    b3 = assign(s2, "HSD-16", emps[2], "500.000")
    credit2 = sale(s2, "HSD-16", emps[2], "100.000", "credit", acme)
    complete(b1, "1500.000")
    complete(b3, "900.000")

    # ---- typed payment-mode totals
    modes = {r["name"]: r["tender_id"] for r in client.get(f"/api/shift-totals/{s1['id']}", headers=h).json()}
    for shift, totals in ((s1, {"DTP Card": "10000.00", "PhonePe": "5000.00", "Paytm": "30000.00"}), (s2, {"PhonePe": "1000.00", "Paytm": "20000.00"})):
        for name, amount in totals.items():
            r = client.put(f"/api/shift-totals/{shift['id']}/{modes[name]}", headers=h, json={"amount": amount, "reference": "slip"})
            assert r.status_code == 200, r.text

    # ---- expenses: tea 150.00 and internal fuel 10 L diesel (= 900.00) in shift 1
    cat = _post(client, h, "/api/expense-categories", {"name": "Tea"})
    _post(client, h, "/api/expenses", {"category_id": cat["id"], "amount": "150.00", "payment_method": "cash", "employee_id": emps[0], "shift_id": s1["id"], "description": "Tea"})
    _post(client, h, "/api/internal-fuel", {"shift_id": s1["id"], "employee_id": emps[0], "fuel_id": fuels["Diesel"], "litres": "10.000", "vehicle": "MH12AB1234"})

    # ---- cash book: Advance + Final = Total Sale - everything else; two bank deposits in shift 1
    _post(client, h, "/api/cash-book/movements", {"shift_id": s1["id"], "advance_amount": "40000.00", "final_amount": "38950.00"})
    _post(client, h, "/api/cash-book/deposits", {"shift_id": s1["id"], "bank_name": "Bank of India", "amount": "50000.00"})
    _post(client, h, "/api/cash-book/deposits", {"shift_id": s1["id"], "bank_name": "Second Bank", "amount": "20000.00"})
    _post(client, h, "/api/cash-book/movements", {"shift_id": s2["id"], "advance_amount": "20000.00", "final_amount": "37750.00"})
    _post(client, h, "/api/cash-book/deposits", {"shift_id": s2["id"], "bank_name": "Bank of India", "amount": "60000.00"})

    # ---- lubricants: opening stock 10 yesterday, purchase 20 today, sales per shift
    racer = _post(client, h, "/api/lubricants", {"name": "HP Racer 1L", "pack_size": "1 ltr", "default_rate": "250.00"})
    milcy = _post(client, h, "/api/lubricants", {"name": "Milcy Turbo 5L", "pack_size": "5 ltr", "default_rate": "1500.00"})
    _post(client, h, f"/api/lubricants/{racer['id']}/movements", {"kind": "opening", "quantity": "10", "movement_date": "2020-01-01"})
    _post(client, h, f"/api/lubricants/{racer['id']}/movements", {"kind": "purchase", "quantity": "20", "movement_date": TODAY})
    _post(client, h, f"/api/lubricants/{racer['id']}/movements", {"kind": "sale", "quantity": "2", "shift_id": s1["id"], "customer_name": "Walk-in"})
    _post(client, h, f"/api/lubricants/{racer['id']}/movements", {"kind": "sale", "quantity": "1", "shift_id": s2["id"], "customer_name": "Walk-in"})
    _post(client, h, f"/api/lubricants/{milcy['id']}/movements", {"kind": "opening", "quantity": "5", "movement_date": "2020-01-01"})
    _post(client, h, f"/api/lubricants/{milcy['id']}/movements", {"kind": "sale", "quantity": "1", "shift_id": s2["id"], "customer_name": "Workshop"})

    # ---- bowser: opening 1,000 L worth 90,000.00; two bills; meter
    _post(client, h, "/api/bowser/opening", {"day": TODAY, "litres": "1000.000", "rupees": "90000.00", "reason": "first day on the app"})
    _post(client, h, "/api/bowser/bills", {"bill_no": "B1", "bill_date": TODAY, "customer_id": beta["id"], "quantity": "150.000", "rate": "95.00", "transport": "500.00", "vehicle_no": "MH14XX0001", "slip_no": "S-1"})
    _post(client, h, "/api/bowser/bills", {"bill_no": "B2", "bill_date": TODAY, "customer_id": beta["id"], "quantity": "250.000", "rate": "95.00", "transport": "1000.00"})
    _post(client, h, "/api/bowser/meter", {"day": TODAY, "start_reading": "1000.000", "testing": "0", "end_reading": "1400.000"})

    # ---- dip readings at the end of the day
    _post(client, h, f"/api/tanks/{tanks['MS-22']['id']}/readings", {"employee_id": emps[0], "physical_stock": "56950.000"})
    _post(client, h, f"/api/tanks/{tanks['HSD-16']['id']}/readings", {"employee_id": emps[2], "physical_stock": "7100.000"})

    return {
        "fuels": fuels, "tanks": tanks, "nozzles": nozzles, "shifts": [s1, s2], "acme": acme, "beta": beta,
        "emps": emps, "transfer": transfer, "credit1": credit1, "credit2": credit2, "racer": racer, "milcy": milcy,
    }


# What the report must say for this day (worked out by hand from the figures above).
EXPECTED = {
    "fuel_rs": [Decimal("144500.00"), Decimal("86000.00")],
    "oil_rs": [Decimal("500.00"), Decimal("1750.00")],
    "total_sale": [Decimal("145000.00"), Decimal("87750.00")],
    "total_rs": Decimal("230500.00"),
    "credit_sale": [Decimal("20000.00"), Decimal("9000.00")],  # 2,000 ACME + 18,000 transfer ; 9,000 ACME
    "expenses": [Decimal("1050.00"), Decimal("0.00")],
}

"""Lubricants, bowser, payment-mode totals and internal fuel: rules, permissions and audit."""

from datetime import date, timedelta
from decimal import Decimal

from api_helpers import audit_chain_ok, audit_events
from pump_day import TODAY
from test_api_daily_report import day  # noqa: F401  (fixture)

D = Decimal


# ------------------------------------------------------------------------------ lubricants
def test_lubricant_rules_permissions_and_audit(client, manager, accountant, attendant, data_entry, session_factory):
    ok = client.post("/api/lubricants", headers=manager, json={"name": "Racer", "pack_size": "1 ltr", "default_rate": "250.00"})
    assert ok.status_code == 201 and ok.json()["stock"] == "0.000"
    item = ok.json()["id"]
    assert client.post("/api/lubricants", headers=manager, json={"name": "Racer", "default_rate": "1.00"}).status_code == 409
    assert client.post("/api/lubricants", headers=accountant, json={"name": "X", "default_rate": "1.00"}).status_code == 403
    assert client.get("/api/lubricants", headers=accountant).status_code == 200  # view only
    assert client.get("/api/lubricants", headers=attendant).status_code == 403
    move = lambda h, **b: client.post(f"/api/lubricants/{item}/movements", headers=h, json=b)  # noqa: E731
    assert move(data_entry, kind="purchase", quantity="12").status_code == 201  # the cashier can enter stock
    assert move(manager, kind="purchase", quantity="0").status_code == 422
    assert move(manager, kind="purchase", quantity="-1").status_code == 422
    assert move(manager, kind="adjustment", quantity="-2").status_code == 422  # a reason is required
    assert move(manager, kind="adjustment", quantity="-2", remarks="leaked can").status_code == 201
    assert move(manager, kind="sale", quantity="1").status_code == 422  # a sale needs its shift
    assert client.get("/api/lubricants", headers=accountant).json()[0]["stock"] == "10.000"
    assert client.post(f"/api/lubricants/{item}/rate", headers=manager, json={"new_rate": "260.00", "reason": "price list"}).json()["default_rate"] == "260.00"
    assert len(client.get(f"/api/lubricants/{item}/movements", headers=manager).json()) == 2
    for event in ("lubricant_item_created", "lubricant_movement_recorded", "lubricant_rate_changed"):
        assert audit_events(session_factory, event), event
    assert audit_chain_ok(session_factory)


def test_a_lubricant_sale_uses_the_item_rate_and_the_shifts_day(client, day, manager):
    racer = day["racer"]["id"]
    sale = client.post(f"/api/lubricants/{racer}/movements", headers=manager, json={"kind": "sale", "quantity": "3", "shift_id": day["shifts"][0]["id"]}).json()
    assert sale["unit_rate"] == "250.00" and sale["amount"] == "750.00" and sale["movement_date"] == TODAY
    custom = client.post(f"/api/lubricants/{racer}/movements", headers=manager, json={"kind": "sale", "quantity": "1.500", "unit_rate": "199.99", "shift_id": day["shifts"][0]["id"]}).json()
    assert custom["amount"] == "299.99"  # 1.5 x 199.99 = 299.985 -> paise, half up


# ------------------------------------------------------------------------------ bowser
def test_bowser_bill_rules_void_and_audit(client, day, manager, accountant, session_factory):
    base = {"bill_no": "B9", "bill_date": TODAY, "customer_id": day["beta"]["id"], "quantity": "10.000", "rate": "95.00", "transport": "50.00"}
    ok = client.post("/api/bowser/bills", headers=manager, json=base)
    assert ok.status_code == 201 and ok.json()["amount"] == "950.00" and ok.json()["total"] == "1000.00"
    assert client.post("/api/bowser/bills", headers=manager, json=base).status_code == 409  # same bill number that day
    assert client.post("/api/bowser/bills", headers=manager, json={**base, "bill_no": "B10", "quantity": "0"}).status_code == 422
    stock_transfer_customer = next(c for c in client.get("/api/customers", headers=manager).json() if c["name"] == "Stock Transfer (Bouser)")
    assert client.post("/api/bowser/bills", headers=manager, json={**base, "bill_no": "B11", "customer_id": stock_transfer_customer["id"]}).status_code == 422
    assert client.post("/api/bowser/bills", headers=accountant, json={**base, "bill_no": "B12"}).status_code == 403
    assert client.get(f"/api/bowser/day?day={TODAY}", headers=accountant).status_code == 200
    bill_id = ok.json()["id"]
    assert client.post(f"/api/bowser/bills/{bill_id}/void", headers=accountant, json={"reason": "x"}).status_code == 403
    assert client.post(f"/api/bowser/bills/{bill_id}/void", headers=manager, json={"reason": "wrong client"}).json()["status"] == "void"
    assert client.post(f"/api/bowser/bills/{bill_id}/void", headers=manager, json={"reason": "again"}).status_code == 409
    bills = client.get(f"/api/bowser/day?day={TODAY}", headers=manager).json()["day_report"]["bills"]
    assert [b["bill_no"] for b in bills] == ["B1", "B2"]  # the voided bill no longer counts, but is kept in the database
    for event in ("bowser_bill_recorded", "bowser_bill_voided", "bowser_transfer_recorded", "bowser_meter_recorded", "bowser_opening_set"):
        assert audit_events(session_factory, event), event
    assert audit_chain_ok(session_factory)


def test_bowser_stock_carries_into_the_next_day(client, day, manager):
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    nxt = client.get(f"/api/bowser/day?day={tomorrow}", headers=manager).json()["day_report"]
    first = nxt["stock_lines"][0]
    # today's closing (1,200 - 400 = 800 L worth 72,000.00 at the 90.00 average) is tomorrow's opening
    assert first["label"] == "Opening Stock" and D(first["litres"]) == D("800") and D(first["rupees"]) == D("72000.00")


def test_bowser_meter_replacement_keeps_the_old_reading_void(client, day, manager, session_factory):
    client.post("/api/bowser/meter", headers=manager, json={"day": TODAY, "start_reading": "1000.000", "testing": "2.000", "end_reading": "1402.000"})
    meter = client.get(f"/api/bowser/day?day={TODAY}", headers=manager).json()["day_report"]["meter"]
    assert D(meter["end_reading"]) == D("1402") and D(meter["testing"]) == D("2")
    s = session_factory()
    from app.models.bowser import BowserMeterReading

    assert s.query(BowserMeterReading).filter_by(status="active").count() == 1
    assert s.query(BowserMeterReading).filter_by(status="void").count() == 1  # the first reading is kept, voided
    s.close()
    assert client.post("/api/bowser/meter", headers=manager, json={"day": TODAY, "start_reading": "10.000", "testing": "0", "end_reading": "5.000"}).status_code == 422


# ------------------------------------------------------------------------------ payment-mode totals
def test_payment_mode_totals_replace_by_voiding_and_refuse_cash_and_credit(client, day, manager, accountant, session_factory):
    s1 = day["shifts"][0]["id"]
    rows = client.get(f"/api/shift-totals/{s1}", headers=accountant).json()
    names = [r["label"] for r in rows]
    assert names == ["CARD", "DTP Card", "Other", "PHONE PAY", "PTM"]  # the old report's wording and order
    paytm = next(r for r in rows if r["label"] == "PTM")
    assert paytm["amount"] == "30000.00"
    again = client.put(f"/api/shift-totals/{s1}/{paytm['tender_id']}", headers=manager, json={"amount": "30500.00", "reason": "slip re-read"})
    assert next(r for r in again.json() if r["label"] == "PTM")["amount"] == "30500.00"
    from app.models.shift_tender_entry import ShiftTenderEntry

    s = session_factory()
    entries = s.query(ShiftTenderEntry).filter_by(tender_id=paytm["tender_id"], shift_id=s1).all()
    assert sorted((e.amount, e.voided_at is not None) for e in entries) == [(D("30000.00"), True), (D("30500.00"), False)]
    assert [e.void_reason for e in entries if e.voided_at][0] == "slip re-read"
    s.close()
    assert client.put(f"/api/shift-totals/{s1}/{paytm['tender_id']}", headers=manager, json={"amount": "-1.00"}).status_code == 422
    assert client.put(f"/api/shift-totals/{s1}/{paytm['tender_id']}", headers=accountant, json={"amount": "1.00"}).status_code == 403
    from app.models.tender import Tender

    s = session_factory()
    cash_id, credit_id = (s.query(Tender).filter_by(name=n).first().id for n in ("Cash", "Credit"))
    s.close()
    for tender_id in (cash_id, credit_id):  # cash comes from the cash book, credit from the bills
        assert client.put(f"/api/shift-totals/{s1}/{tender_id}", headers=manager, json={"amount": "1.00"}).status_code == 422
    assert audit_events(session_factory, "shift_tender_total_set")


# ------------------------------------------------------------------------------ internal fuel use
def test_internal_fuel_needs_a_price_and_never_deducts_stock(client, day, manager, owner, session_factory):
    shift, emp, diesel = day["shifts"][1], day["emps"][0], day["fuels"]["Diesel"]
    before = D(client.get(f"/api/tanks/{day['tanks']['HSD-22']['id']}", headers=manager).json()["current_stock"])
    ok = client.post("/api/internal-fuel", headers=manager, json={"shift_id": shift["id"], "employee_id": emp, "fuel_id": diesel, "litres": "40.000", "vehicle": "Genset"})
    assert ok.status_code == 201 and ok.json()["rate"] == "90.00"
    expense = next(e for e in client.get("/api/expenses", headers=manager).json() if e["id"] == ok.json()["expense_id"])
    assert expense["amount"] == "3600.00" and expense["description"] == "Diesel Exp (Genset) 40 Lit" and expense["status"] == "pending"
    assert D(client.get(f"/api/tanks/{day['tanks']['HSD-22']['id']}", headers=manager).json()["current_stock"]) == before
    assert client.post("/api/internal-fuel", headers=manager, json={"shift_id": shift["id"], "employee_id": emp, "fuel_id": diesel, "litres": "1.000", "vehicle": " "}).status_code == 422
    assert client.put("/api/pump-settings/internal_fuel_deducts_tank", headers=owner, json={"value": "on"}).status_code == 200
    blocked = client.post("/api/internal-fuel", headers=manager, json={"shift_id": shift["id"], "employee_id": emp, "fuel_id": diesel, "litres": "1.000", "vehicle": "Omni"})
    assert blocked.status_code == 409 and "T-12" in blocked.json()["error"]["message"]
    assert audit_events(session_factory, "internal_fuel_use_recorded") and audit_chain_ok(session_factory)

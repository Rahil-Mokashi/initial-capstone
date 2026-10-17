from datetime import date

import pytest

from api_helpers import audit_chain_ok, audit_events


@pytest.fixture()
def pump(client, manager, fuel_id, tank, employee_id):
    """A priced fuel, a nozzle on the tank, an open shift and an active assignment."""
    client.post(f"/api/fuel-prices/{fuel_id}/rate", headers=manager, json={"new_rate_per_liter": "100.00"})
    d = client.post("/api/dispensers", headers=manager, json={"code": "D1"}).json()
    n = client.post("/api/nozzles", headers=manager, json={"code": "N1", "dispenser_id": d["id"], "fuel_id": fuel_id, "tank_id": tank["id"]}).json()
    s = client.post("/api/shifts", headers=manager, json={"shift_date": date.today().isoformat(), "shift_label": "Morning"}).json()
    a = client.post(f"/api/shifts/{s['id']}/assignments", headers=manager, json={"employee_id": employee_id, "nozzle_id": n["id"], "opening_meter": "0"})
    assert a.status_code == 201, a.text
    return {"shift": s, "nozzle": n, "employee_id": employee_id, "tank": tank}


def _sale(client, h, pump, **over):
    body = {"shift_id": pump["shift"]["id"], "nozzle_id": pump["nozzle"]["id"], "employee_id": pump["employee_id"], "quantity": "10.000", "payment_method": "cash"}
    return client.post("/api/sales", headers=h, json={**body, **over})


def test_options_for_a_manager(client, manager, pump):
    o = client.get("/api/sales/options", headers=manager).json()
    assert o["can_pick_freely"] is True and o["shifts"] and o["nozzles"][0]["label"] == "N1" and o["employees"]


def test_record_sale_snapshots_rate_moves_stock_and_lists(client, manager, accountant, pump, session_factory):
    r = _sale(client, manager, pump)
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["rate_per_liter"] == "100.00" and s["amount"] == "1000.00" and s["quantity"] == "10.000"
    assert s["payment_status"] and s["fuel_type"] and s["nozzle"] == "N1" and s["status"] == "completed"
    assert client.get(f"/api/tanks/{pump['tank']['id']}", headers=manager).json()["current_stock"] == "2490.500"
    page = client.get("/api/sales?limit=10&offset=0", headers=accountant).json()
    assert page["total"] == 1 and page["items"][0]["receipt_number"] == s["receipt_number"]
    # a later price change never alters the old sale
    client.post(f"/api/fuel-prices/{pump['nozzle']['fuel_id']}/rate", headers=manager, json={"new_rate_per_liter": "120.00"})
    again = client.get("/api/sales", headers=accountant).json()["items"][0]
    assert again["amount"] == "1000.00"
    assert len(audit_events(session_factory, "sale_recorded")) == 1 and audit_chain_ok(session_factory)


def test_sale_validation_and_permissions(client, manager, accountant, pump):
    assert _sale(client, manager, pump, quantity="0").status_code == 422
    assert _sale(client, manager, pump, quantity=10).status_code == 422
    assert _sale(client, manager, pump, payment_method="barter").status_code == 422
    assert _sale(client, manager, pump, payment_method="credit").status_code in (409, 422)  # needs a customer
    assert _sale(client, accountant, pump).status_code == 403
    assert client.get("/api/sales", headers=accountant).status_code == 200


def test_cancel_sale_restores_stock_and_payment_actions(client, manager, pump, session_factory):
    s = _sale(client, manager, pump, payment_method="upi", reference_number="UPI-1").json()
    assert client.post(f"/api/payments/{s['payment_id']}/mark-failed", headers=manager, json={}).json()["status"] == "failed"
    c = client.post(f"/api/sales/{s['id']}/cancel", headers=manager, json={})
    assert c.status_code == 200 and c.json()["status"] == "cancelled"
    assert client.get(f"/api/tanks/{pump['tank']['id']}", headers=manager).json()["current_stock"] == "2500.500"
    assert client.post(f"/api/sales/{s['id']}/cancel", headers=manager, json={}).status_code in (409, 422)
    assert client.post("/api/payments/nope/refund", headers=manager, json={}).status_code == 404
    assert audit_chain_ok(session_factory)


def test_receipt_html_and_pdf(client, manager, accountant, pump):
    s = _sale(client, manager, pump).json()
    r = client.get(f"/api/sales/{s['id']}/receipt", headers=accountant).json()
    assert s["receipt_number"] in r["html"] and r["filename"] == f"receipt_{s['receipt_number']}.pdf"
    pdf = client.get(f"/api/sales/{s['id']}/receipt.pdf", headers=accountant)
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf" and pdf.content.startswith(b"%PDF")
    assert client.get("/api/sales/nope/receipt", headers=accountant).status_code == 404


def test_today_by_fuel_cards(client, manager, accountant, pump):
    assert client.get("/api/sales/today-by-fuel", headers=accountant).json() == []
    # sale_at is "now", so a sale made today shows up under today's report
    _sale(client, manager, pump)
    cards = client.get("/api/sales/today-by-fuel", headers=accountant).json()
    assert cards and cards[0]["amount"] == "1000.00" and cards[0]["quantity"] == "10.00"


def test_customers(client, manager, accountant, session_factory):
    c = client.post("/api/customers", headers=manager, json={"name": "ACME Transport", "phone": "99999"})
    assert c.status_code == 201 and c.json()["status"] == "active"
    assert client.post("/api/customers", headers=manager, json={"name": " "}).status_code == 422
    off = client.post(f"/api/customers/{c.json()['id']}/status", headers=manager, json={"status": "inactive"})
    assert off.json()["status"] == "inactive"
    assert client.post("/api/customers", headers=accountant, json={"name": "X"}).status_code == 403
    assert [x["name"] for x in client.get("/api/customers", headers=accountant).json()] == ["ACME Transport"]
    opts = client.get("/api/sales/options", headers=manager).json()
    assert opts["customers"] == []  # inactive customers are not offered
    assert audit_chain_ok(session_factory)


def test_attendant_sells_from_their_own_assignment(client, session_factory, manager, attendant, fuel_id, tank, attendant_sales_on):
    # Link the attendant user to an employee with an active assignment.
    from app.models.employee import Employee
    from app.models.user import User

    db = session_factory()
    try:
        user = db.query(User).filter_by(username="attendant1").first()
        emp = Employee(
            employee_code="EMP-0009", first_name="Att", last_name="Endant", contact_number="9876543210",
            joining_date=__import__("datetime").date(2026, 1, 1), user_id=user.id,
        )
        db.add(emp)
        db.commit()
        emp_id = emp.id
    finally:
        db.close()
    client.post(f"/api/fuel-prices/{fuel_id}/rate", headers=manager, json={"new_rate_per_liter": "100.00"})
    d = client.post("/api/dispensers", headers=manager, json={"code": "D1"}).json()
    n = client.post("/api/nozzles", headers=manager, json={"code": "N1", "dispenser_id": d["id"], "fuel_id": fuel_id, "tank_id": tank["id"]}).json()
    s = client.post("/api/shifts", headers=manager, json={"shift_date": date.today().isoformat(), "shift_label": "Morning"}).json()
    client.post(f"/api/shifts/{s['id']}/assignments", headers=manager, json={"employee_id": emp_id, "nozzle_id": n["id"], "opening_meter": "0"})
    opts = client.get("/api/sales/options", headers=attendant).json()
    assert opts["can_pick_freely"] is False and opts["my_assignment"]["nozzle"] == "N1"
    sale = client.post("/api/sales/mine", headers=attendant, json={"quantity": "5", "payment_method": "cash"})
    assert sale.status_code == 201 and sale.json()["amount"] == "500.00"


def test_attendant_without_assignment_cannot_sell(client, attendant, attendant_sales_on):
    o = client.get("/api/sales/options", headers=attendant).json()
    assert o["can_pick_freely"] is False and o["my_assignment"] is None
    assert client.post("/api/sales/mine", headers=attendant, json={"quantity": "5", "payment_method": "cash"}).status_code == 422

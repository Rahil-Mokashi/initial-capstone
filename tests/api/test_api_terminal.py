from datetime import date

import pytest

from test_api_sales import pump  # noqa: F401  (fixture)


def test_context_for_a_manager_lists_rates(client, manager, pump):
    c = client.get("/api/terminal/context", headers=manager).json()
    assert c["can_pick_freely"] is True and c["shifts"] and c["employees"]
    assert c["nozzles"][0]["code"] == "N1" and c["nozzles"][0]["rate_per_liter"] == "100.00"


def _sale(client, h, pump, **over):
    body = {"mode": "amount", "vehicle_number": "MH12AB1234", "value": "500.00", "payment_method": "cash", "shift_id": pump["shift"]["id"], "nozzle_id": pump["nozzle"]["id"], "employee_id": pump["employee_id"]}
    return client.post("/api/terminal/sales", headers=h, json={**body, **over})


def test_amount_mode_derives_the_quantity_from_the_rate(client, manager, pump):
    r = _sale(client, manager, pump)
    assert r.status_code == 201, r.text
    assert r.json()["quantity"] == "5.000" and r.json()["amount"] == "500.00"
    assert client.get(f"/api/tanks/{pump['tank']['id']}", headers=manager).json()["current_stock"] == "2495.500"


def test_amount_that_does_not_divide_evenly_keeps_the_service_rounding(client, manager, pump, fuel_id):
    client.post(f"/api/fuel-prices/{fuel_id}/rate", headers=manager, json={"new_rate_per_liter": "103.50"})
    r = _sale(client, manager, pump, value="500.00")
    assert r.status_code == 201, r.text
    assert r.json()["quantity"] == "4.831"  # 500 / 103.50 stored to a millilitre


def test_litres_mode_and_credit_rule(client, manager, pump):
    r = _sale(client, manager, pump, mode="litres", value="12.50")
    assert r.status_code == 201 and r.json()["quantity"] == "12.500" and r.json()["amount"] == "1250.00"
    credit = _sale(client, manager, pump, payment_method="credit")
    assert credit.status_code in (409, 422)


def test_free_pick_needs_shift_nozzle_and_attendant(client, manager, pump):
    r = client.post("/api/terminal/sales", headers=manager, json={"mode": "amount", "vehicle_number": "MH12AB1234", "value": "100", "payment_method": "cash"})
    assert r.status_code == 422


def test_attendant_uses_their_own_assignment(client, session_factory, manager, attendant, fuel_id, tank):
    import datetime

    from app.models.employee import Employee
    from app.models.user import User

    db = session_factory()
    try:
        user = db.query(User).filter_by(username="attendant1").first()
        emp = Employee(employee_code="EMP-0009", first_name="Att", last_name="Endant", contact_number="9876543210", joining_date=datetime.date(2026, 1, 1), user_id=user.id)
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
    ctx = client.get("/api/terminal/context", headers=attendant).json()
    assert ctx["can_pick_freely"] is False and ctx["my_assignment"]["nozzle"]["code"] == "N1"
    sale = client.post("/api/terminal/sales", headers=attendant, json={"mode": "amount", "vehicle_number": "MH12AB1234", "value": "200", "payment_method": "cash"})
    assert sale.status_code == 201 and sale.json()["quantity"] == "2.000"


def test_unassigned_attendant_cannot_sell(client, attendant):
    ctx = client.get("/api/terminal/context", headers=attendant).json()
    assert ctx["my_assignment"] is None
    assert client.post("/api/terminal/sales", headers=attendant, json={"mode": "amount", "vehicle_number": "MH12AB1234", "value": "200", "payment_method": "cash"}).status_code == 422

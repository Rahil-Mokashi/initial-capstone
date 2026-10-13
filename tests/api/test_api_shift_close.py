"""Shift close entry: closing master readings typed in one go, with no attendant named and no per-sale records."""

from decimal import Decimal

from api_helpers import audit_chain_ok, audit_events
from pump_day import TODAY

D = Decimal


def _setup(client, h):
    fuels = {f["fuel_type"]: f["id"] for f in client.get("/api/lookups/fuels", headers=h).json()}
    client.post(f"/api/fuel-prices/{fuels['Petrol']}/rate", headers=h, json={"new_rate_per_liter": "100.00"})
    tank = client.post("/api/tanks", headers=h, json={"code": "MS-22", "fuel_id": fuels["Petrol"], "capacity": "50000", "opening_stock": "10000"}).json()
    d = client.post("/api/dispensers", headers=h, json={"code": "D1"}).json()
    nozzles = [client.post("/api/nozzles", headers=h, json={"code": c, "dispenser_id": d["id"], "fuel_id": fuels["Petrol"], "tank_id": tank["id"]}).json() for c in ("N1", "N2")]
    shift = client.post("/api/shifts", headers=h, json={"shift_date": TODAY, "shift_label": "Morning"}).json()
    return nozzles, shift, tank


def test_type_the_closing_readings_and_the_cash_sale_appears_without_naming_anyone(client, data_entry, manager, owner, session_factory):
    nozzles, shift, tank = _setup(client, manager)
    first = client.get(f"/api/shift-close/{shift['id']}", headers=data_entry).json()
    assert [(l["code"], l["opening"], l["closed"]) for l in first] == [("N1", None, False), ("N2", None, False)]
    # the first time a nozzle is ever used its opening reading is typed too
    refused = client.post(f"/api/shift-close/{shift['id']}", headers=data_entry, json={"readings": [{"nozzle_id": nozzles[0]["id"], "closing": "500.000"}]})
    assert refused.status_code == 422 and "opening" in refused.json()["error"]["message"]
    ok = client.post(f"/api/shift-close/{shift['id']}", headers=data_entry, json={"readings": [
        {"nozzle_id": nozzles[0]["id"], "opening": "1000.000", "closing": "1500.000", "testing": "5.000"},
        {"nozzle_id": nozzles[1]["id"], "opening": "0", "closing": "200.000"}]})
    assert ok.status_code == 200, ok.text
    assert [(l["code"], l["closed"], l["closing"]) for l in ok.json()] == [("N1", True, "1500.000"), ("N2", True, "200.000")]
    sales = client.get("/api/sales", headers=manager).json()["items"]
    assert sorted((s["nozzle"], s["quantity"], s["amount"], s["payment_method"]) for s in sales) == [
        ("N1", "495.000", "49500.00", "cash"), ("N2", "200.000", "20000.00", "cash")]  # 500 - 5 testing, and 200, billed as cash
    assert D(client.get(f"/api/tanks/{tank['id']}", headers=manager).json()["current_stock"]) == D("10000") - D("695")
    assert audit_events(session_factory, "shift_close_entry") and audit_chain_ok(session_factory)
    # the checks see it: litres billed equal the meters less testing
    client.post("/api/checks/run", headers=owner, json={"day": TODAY})
    litres = [c for c in client.get(f"/api/checks?day={TODAY}", headers=owner).json()["results"] if c["key"] == "shift.litres_match_meters"]
    assert litres and litres[0]["status"] == "pass" and litres[0]["actual"] == "695.000"


def test_the_next_shift_starts_where_the_last_one_closed_and_a_closed_nozzle_cannot_be_closed_twice(client, data_entry, manager):
    nozzles, shift, _ = _setup(client, manager)
    r = [{"nozzle_id": nozzles[0]["id"], "opening": "1000.000", "closing": "1500.000"}]
    assert client.post(f"/api/shift-close/{shift['id']}", headers=data_entry, json={"readings": r}).status_code == 200
    again = client.post(f"/api/shift-close/{shift['id']}", headers=data_entry, json={"readings": [{"nozzle_id": nozzles[0]["id"], "closing": "1600.000"}]})
    assert again.status_code == 409 and "already closed" in again.json()["error"]["message"]
    evening = client.post("/api/shifts", headers=manager, json={"shift_date": TODAY, "shift_label": "Evening"}).json()
    sheet = client.get(f"/api/shift-close/{evening['id']}", headers=data_entry).json()
    assert next(l for l in sheet if l["code"] == "N1")["opening"] == "1500.000"  # last closing carries forward
    below = client.post(f"/api/shift-close/{evening['id']}", headers=data_entry, json={"readings": [{"nozzle_id": nozzles[0]["id"], "closing": "1400.000"}]})
    assert below.status_code == 422 and "below the opening" in below.json()["error"]["message"]
    ok = client.post(f"/api/shift-close/{evening['id']}", headers=data_entry, json={"readings": [{"nozzle_id": nozzles[0]["id"], "closing": "1750.000"}]})
    assert ok.status_code == 200


def test_permissions(client, data_entry, manager, attendant, accountant):
    _, shift, _ = _setup(client, manager)
    assert client.get(f"/api/shift-close/{shift['id']}", headers=attendant).status_code == 403
    assert client.post(f"/api/shift-close/{shift['id']}", headers=accountant, json={"readings": []}).status_code == 403
    assert client.post(f"/api/shift-close/{shift['id']}", headers=data_entry, json={"readings": []}).status_code == 422
    assert client.get(f"/api/shift-close/{shift['id']}", headers={"X-Launch-Secret": client.headers["X-Launch-Secret"]}).status_code == 401

import re
from decimal import Decimal

import pytest

from api.schemas import MoneyOut, PercentOut, VolumeOut
from api_helpers import audit_chain_ok, audit_events
from pydantic import BaseModel

VOLUME_3DP = re.compile(r"^-?\d+\.\d{3}$")
TWO_DP = re.compile(r"^-?\d+\.\d{2}$")


# ---- reads -------------------------------------------------------------------
def test_list_tanks_success_and_decimal_strings(client, manager, tank):
    resp = client.get("/api/tanks", headers=manager)
    assert resp.status_code == 200
    [row] = resp.json()
    assert row["code"] == "T1" and row["fuel_type"]
    for key in ("capacity", "current_stock", "opening_stock"):
        assert isinstance(row[key], str) and VOLUME_3DP.match(row[key]), (key, row[key])
    assert row["capacity"] == "10000.000" and row["current_stock"] == "2500.500"
    assert row["fill_percent"] == "25.01" and TWO_DP.match(row["fill_percent"])
    assert row["is_low"] is False


def test_list_tanks_is_403_for_a_role_without_inventory_view(client, attendant, tank, session_factory):
    resp = client.get("/api/tanks", headers=attendant)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "permission_denied"
    assert resp.json()["error"]["details"]["permission"] == "inventory.view"
    assert len(audit_events(session_factory, "permission_denied")) >= 1  # denial is audited
    assert audit_chain_ok(session_factory)


def test_view_only_role_can_read(client, accountant, tank):
    assert client.get("/api/tanks", headers=accountant).status_code == 200
    assert client.get(f"/api/tanks/{tank['id']}", headers=accountant).status_code == 200


def test_get_tank_and_404(client, manager, tank):
    assert client.get(f"/api/tanks/{tank['id']}", headers=manager).json()["id"] == tank["id"]
    missing = client.get("/api/tanks/does-not-exist", headers=manager)
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"


def test_get_tank_403(client, attendant, tank):
    assert client.get(f"/api/tanks/{tank['id']}", headers=attendant).status_code == 403


def test_recent_transactions_empty_then_populated(client, manager, tank):
    assert client.get("/api/tanks/recent-transactions", headers=manager).json() == []
    client.post(f"/api/tanks/{tank['id']}/transactions", headers=manager,
                json={"transaction_type": "receipt", "quantity": "100"})
    [row] = client.get("/api/tanks/recent-transactions?limit=5", headers=manager).json()
    assert row["tank_code"] == "T1" and row["quantity"] == "100.000"


def test_recent_transactions_403_and_422(client, attendant, manager):
    assert client.get("/api/tanks/recent-transactions", headers=attendant).status_code == 403
    assert client.get("/api/tanks/recent-transactions?limit=0", headers=manager).status_code == 422


# ---- create tank -------------------------------------------------------------------
def test_create_tank_writes_audit_and_keeps_chain(client, session_factory, manager, fuel_id):
    resp = client.post("/api/tanks", headers=manager,
                       json={"code": " T9 ", "fuel_id": fuel_id, "capacity": "5000.250", "calibration_info": "chart A"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["code"] == "T9" and body["capacity"] == "5000.250" and body["current_stock"] == "0.000"
    [entry] = audit_events(session_factory, "tank_created")
    assert entry.entity_id == body["id"]
    assert audit_chain_ok(session_factory)


def test_create_tank_403_for_view_only(client, accountant, fuel_id, session_factory):
    resp = client.post("/api/tanks", headers=accountant, json={"code": "T2", "fuel_id": fuel_id, "capacity": "100"})
    assert resp.status_code == 403
    assert audit_events(session_factory, "tank_created") == []


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"code": "T2", "fuel_id": "f"},  # capacity missing
        {"code": "T2", "fuel_id": "f", "capacity": 100},  # number, not string
        {"code": "T2", "fuel_id": "f", "capacity": "1.2345"},  # more places than the column stores
        {"code": "T2", "fuel_id": "f", "capacity": "abc"},
        {"code": "T2", "fuel_id": "f", "capacity": "NaN"},
        {"code": "T2", "fuel_id": "f", "capacity": "1", "surprise": "x"},
    ],
)
def test_create_tank_422(client, manager, body):
    resp = client.post("/api/tanks", headers=manager, json=body)
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "validation_error"


def test_create_tank_rule_errors(client, manager, tank, fuel_id):
    zero = client.post("/api/tanks", headers=manager, json={"code": "T3", "fuel_id": fuel_id, "capacity": "0"})
    assert zero.status_code == 422 and zero.json()["error"]["details"]["fields"]
    dup = client.post("/api/tanks", headers=manager, json={"code": "T1", "fuel_id": fuel_id, "capacity": "10"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "conflict"
    over = client.post("/api/tanks", headers=manager,
                       json={"code": "T4", "fuel_id": fuel_id, "capacity": "10", "opening_stock": "11"})
    assert over.status_code == 409
    nofuel = client.post("/api/tanks", headers=manager, json={"code": "T5", "fuel_id": "zzz", "capacity": "10"})
    assert nofuel.status_code == 404


# ---- status ---------------------------------------------------------------------------
def test_set_status_success_audit(client, manager, tank, session_factory):
    resp = client.post(f"/api/tanks/{tank['id']}/status", headers=manager,
                       json={"status": "maintenance", "reason": "Pump service"})
    assert resp.status_code == 200 and resp.json()["status"] == "maintenance"
    [entry] = audit_events(session_factory, "tank_status_changed")
    assert entry.description == "Pump service" and entry.old_value == "active" and entry.new_value == "maintenance"
    assert audit_chain_ok(session_factory)


def test_set_status_403_422(client, accountant, manager, tank):
    assert client.post(f"/api/tanks/{tank['id']}/status", headers=accountant,
                       json={"status": "inactive", "reason": "x"}).status_code == 403
    assert client.post(f"/api/tanks/{tank['id']}/status", headers=manager,
                       json={"status": "exploded", "reason": "x"}).status_code == 422
    blank = client.post(f"/api/tanks/{tank['id']}/status", headers=manager, json={"status": "inactive", "reason": "  "})
    assert blank.status_code == 200  # reason optional (owner decision)


# ---- transactions -----------------------------------------------------------------------
def test_receipt_issue_adjustment_move_stock_and_audit(client, manager, tank, session_factory):
    tid = tank["id"]
    r = client.post(f"/api/tanks/{tid}/transactions", headers=manager,
                    json={"transaction_type": "receipt", "quantity": "1000.5", "reference": "INV-1"})
    assert r.status_code == 201 and r.json()["quantity"] == "1000.500" and r.json()["recorded_by"] == "manager1"
    i = client.post(f"/api/tanks/{tid}/transactions", headers=manager, json={"transaction_type": "issue", "quantity": "200"})
    assert i.json()["quantity"] == "-200.000"  # sign convention comes from the service
    a = client.post(f"/api/tanks/{tid}/transactions", headers=manager,
                    json={"transaction_type": "adjustment", "quantity": "-0.5", "remarks": "dip correction"})
    assert a.status_code == 201
    assert client.get(f"/api/tanks/{tid}", headers=manager).json()["current_stock"] == "3300.500"
    assert len(client.get(f"/api/tanks/{tid}/transactions", headers=manager).json()) == 3
    assert len(audit_events(session_factory, "tank_transaction_recorded")) == 3
    assert audit_chain_ok(session_factory)


def test_transaction_403_and_list_403(client, accountant, attendant, tank):
    tid = tank["id"]
    assert client.post(f"/api/tanks/{tid}/transactions", headers=accountant,
                       json={"transaction_type": "receipt", "quantity": "1"}).status_code == 403
    assert client.get(f"/api/tanks/{tid}/transactions", headers=attendant).status_code == 403
    assert client.get(f"/api/tanks/{tid}/transactions", headers=accountant).status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"transaction_type": "receipt"},
        {"transaction_type": "teleport", "quantity": "1"},
        {"transaction_type": "internal_consumption", "quantity": "1"},  # not offered by the Qt screen
        {"transaction_type": "receipt", "quantity": 5},
        {"transaction_type": "receipt", "quantity": "0"},
        {"transaction_type": "receipt", "quantity": "1.0001"},
    ],
)
def test_transaction_422(client, manager, tank, body):
    assert client.post(f"/api/tanks/{tank['id']}/transactions", headers=manager, json=body).status_code == 422


def test_transaction_business_rules(client, manager, tank, session_factory):
    tid = tank["id"]
    over = client.post(f"/api/tanks/{tid}/transactions", headers=manager,
                       json={"transaction_type": "receipt", "quantity": "9000"})
    assert over.status_code == 409 and "capacity" in over.json()["error"]["message"]
    under = client.post(f"/api/tanks/{tid}/transactions", headers=manager,
                        json={"transaction_type": "issue", "quantity": "99999"})
    assert under.status_code == 409
    noreason = client.post(f"/api/tanks/{tid}/transactions", headers=manager,
                           json={"transaction_type": "adjustment", "quantity": "5"})
    assert noreason.status_code == 201  # adjustment reason optional; stored as "No reason given"
    unknown = client.post("/api/tanks/nope/transactions", headers=manager,
                          json={"transaction_type": "receipt", "quantity": "1"})
    assert unknown.status_code == 404
    # rejected writes leave no trace in stock or in the audit trail
    assert client.get(f"/api/tanks/{tid}", headers=manager).json()["current_stock"] == "2505.500"  # only the reason-less adjustment (+5) landed
    assert len(audit_events(session_factory, "tank_transaction_recorded")) == 1  # just the adjustment


# ---- readings ---------------------------------------------------------------------------------
def test_record_reading_success_audit_and_list(client, manager, tank, employee_id, session_factory):
    tid = tank["id"]
    resp = client.post(f"/api/tanks/{tid}/readings", headers=manager,
                       json={"employee_id": employee_id, "physical_stock": "2490.125", "dip_value": "123.4", "remarks": "morning"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["physical_stock"] == "2490.125" and body["dip_value"] == "123.400"
    assert body["employee_name"] == "Ravi Kumar"
    [listed] = client.get(f"/api/tanks/{tid}/readings", headers=manager).json()
    assert listed["id"] == body["id"]
    assert len(audit_events(session_factory, "tank_reading_recorded")) == 1
    assert audit_chain_ok(session_factory)
    # a reading is an observation: it must not move the book stock
    assert client.get(f"/api/tanks/{tid}", headers=manager).json()["current_stock"] == "2500.500"


def test_reading_dip_is_optional(client, manager, tank, employee_id):
    resp = client.post(f"/api/tanks/{tank['id']}/readings", headers=manager,
                       json={"employee_id": employee_id, "physical_stock": "10"})
    assert resp.status_code == 201 and resp.json()["dip_value"] is None


def test_reading_403_and_422_and_404(client, manager, accountant, attendant, tank, employee_id):
    tid = tank["id"]
    ok = {"employee_id": employee_id, "physical_stock": "5"}
    assert client.post(f"/api/tanks/{tid}/readings", headers=accountant, json=ok).status_code == 403
    assert client.get(f"/api/tanks/{tid}/readings", headers=attendant).status_code == 403
    assert client.post(f"/api/tanks/{tid}/readings", headers=manager, json={}).status_code == 422
    assert client.post(f"/api/tanks/{tid}/readings", headers=manager,
                       json={"employee_id": employee_id, "physical_stock": "-1"}).status_code == 422
    assert client.post(f"/api/tanks/{tid}/readings", headers=manager,
                       json={"employee_id": employee_id, "physical_stock": 5}).status_code == 422
    assert client.post(f"/api/tanks/{tid}/readings", headers=manager,
                       json={"employee_id": "ghost", "physical_stock": "5"}).status_code == 404


# ---- reconciliation ------------------------------------------------------------------------------
def test_reconciliation_success_resets_stock_audit(client, manager, tank, session_factory):
    tid = tank["id"]
    client.post(f"/api/tanks/{tid}/transactions", headers=manager,
                json={"transaction_type": "issue", "quantity": "500"})
    resp = client.post(f"/api/tanks/{tid}/reconciliations", headers=manager,
                       json={"reconciliation_date": "2099-01-01", "physical_stock": "1990.500", "remarks": "month end"})
    assert resp.status_code == 201
    rec = resp.json()
    assert rec["expected_closing_stock"] == "2000.500" and rec["variance"] == "-10.000"
    assert TWO_DP.match(rec["variance_percent"]) and rec["classification"]
    for key in ("opening_stock", "received_quantity", "sold_quantity", "testing_quantity", "physical_stock"):
        assert VOLUME_3DP.match(rec[key]), key
    assert client.get(f"/api/tanks/{tid}", headers=manager).json()["current_stock"] == "1990.500"
    assert len(client.get(f"/api/tanks/{tid}/reconciliations", headers=manager).json()) == 1
    assert len(audit_events(session_factory, "fuel_reconciliation_performed")) == 1
    assert audit_chain_ok(session_factory)


def test_reconciliation_403_422(client, manager, accountant, attendant, tank):
    tid = tank["id"]
    good = {"reconciliation_date": "2099-01-01", "physical_stock": "5"}
    assert client.post(f"/api/tanks/{tid}/reconciliations", headers=accountant, json=good).status_code == 403
    assert client.get(f"/api/tanks/{tid}/reconciliations", headers=attendant).status_code == 403
    assert client.post(f"/api/tanks/{tid}/reconciliations", headers=manager, json={"physical_stock": "5"}).status_code == 422
    assert client.post(f"/api/tanks/{tid}/reconciliations", headers=manager,
                       json={"reconciliation_date": "not-a-date", "physical_stock": "5"}).status_code == 422
    assert client.post(f"/api/tanks/{tid}/reconciliations", headers=manager,
                       json={"reconciliation_date": "2099-01-01", "physical_stock": "-5"}).status_code == 422


# ---- lookups ---------------------------------------------------------------------------------------
def test_lookups(client, manager, accountant, attendant, employee_id):
    fuels = client.get("/api/lookups/fuels", headers=manager)
    assert fuels.status_code == 200 and fuels.json() and {"id", "fuel_type"} == set(fuels.json()[0])
    assert client.get("/api/lookups/fuels", headers=accountant).status_code == 403  # no INVENTORY_MANAGE
    emps = client.get("/api/lookups/employees", headers=manager)
    assert emps.status_code == 200 and emps.json()[0]["employee_code"] == "EMP-0001"
    assert client.get("/api/lookups/employees", headers=attendant).status_code == 403


# ---- serialization contract -------------------------------------------------------------------------
class _Probe(BaseModel):
    money: MoneyOut
    volume: VolumeOut
    pct: PercentOut


def test_decimals_serialize_as_strings_at_the_right_scale():
    probe = _Probe(money=Decimal("12.345"), volume=Decimal("1.0005"), pct=Decimal("25.005"))
    data = probe.model_dump(mode="json")
    assert data == {"money": "12.35", "volume": "1.001", "pct": "25.01"}  # half-up, never banker's
    assert all(isinstance(v, str) for v in data.values())
    assert _Probe(money=1, volume=2, pct=3).model_dump(mode="json") == {"money": "1.00", "volume": "2.000", "pct": "3.00"}
    assert '"12.35"' in probe.model_dump_json()  # a JSON string, not a JSON number


def test_no_decimal_ever_leaves_as_a_json_number(client, manager, tank, employee_id):
    tid = tank["id"]
    client.post(f"/api/tanks/{tid}/transactions", headers=manager, json={"transaction_type": "receipt", "quantity": "10"})
    client.post(f"/api/tanks/{tid}/readings", headers=manager, json={"employee_id": employee_id, "physical_stock": "9"})
    client.post(f"/api/tanks/{tid}/reconciliations", headers=manager, json={"reconciliation_date": "2099-01-01", "physical_stock": "9"})
    for path in ("/api/tanks", f"/api/tanks/{tid}", f"/api/tanks/{tid}/transactions", f"/api/tanks/{tid}/readings",
                 f"/api/tanks/{tid}/reconciliations", "/api/tanks/recent-transactions"):
        data = client.get(path, headers=manager).json()
        for row in data if isinstance(data, list) else [data]:
            for key, value in row.items():
                assert not (isinstance(value, (int, float)) and not isinstance(value, bool)), (path, key, value)


def test_unexpected_error_is_500_with_generic_message(session_factory, users, secret):
    from fastapi.testclient import TestClient

    from api.app import create_app
    from api.errors import GENERIC_ERROR_MESSAGE

    app = create_app(secret, session_factory=session_factory, session_timeout_hours=8)

    @app.get("/api/boom")
    def boom():
        raise RuntimeError("secret internals: /path/to/db")

    c = TestClient(app, base_url="http://127.0.0.1", headers={"X-Launch-Secret": secret}, raise_server_exceptions=False)
    resp = c.get("/api/boom")
    assert resp.status_code == 500
    assert resp.json()["error"] == {"code": "internal_error", "message": GENERIC_ERROR_MESSAGE, "details": {}}
    assert "internals" not in resp.text


def test_a_tank_reports_how_high_its_fuel_stands_and_a_dip_chart_changes_it(client, manager, accountant, fuel_id):
    tank = client.post("/api/tanks", headers=manager, json={"code": "MS-22", "fuel_id": fuel_id, "capacity": "20000", "opening_stock": "10000"}).json()
    plain = client.get(f"/api/tanks/{tank['id']}", headers=accountant).json()
    assert plain["fill_basis"] == "round_tank" and plain["has_dip_chart"] is False
    assert abs(float(plain["fill_height"]) - 0.5) < 0.001  # half the fuel of a round tank stands at half height
    # the oil company's chart: 100 cm tall, but with the middle holding less than a round tank would
    chart = {"rows": [{"dip_cm": "0", "litres": "0"}, {"dip_cm": "50", "litres": "5000"}, {"dip_cm": "100", "litres": "20000"}]}
    assert client.put(f"/api/tanks/{tank['id']}/dip-chart", headers=accountant, json=chart).status_code == 403
    assert client.put(f"/api/tanks/{tank['id']}/dip-chart", headers=manager, json=chart).status_code == 200
    after = client.get(f"/api/tanks/{tank['id']}", headers=accountant).json()
    assert after["fill_basis"] == "dip_chart" and after["has_dip_chart"] is True
    assert abs(float(after["fill_height"]) - (50 + 50 * 5000 / 15000) / 100) < 0.001  # 10,000 L is between 5,000 and 20,000 L
    assert [r["dip_cm"] for r in client.get(f"/api/tanks/{tank['id']}/dip-chart", headers=accountant).json()] == ["0.0", "50.0", "100.0"]


def test_a_dip_chart_must_make_sense_and_the_old_one_stays_on_record(client, manager, fuel_id, session_factory):
    from api_helpers import audit_chain_ok, audit_events
    from app.models.tank_dip_chart import TankDipChartPoint

    tank = client.post("/api/tanks", headers=manager, json={"code": "HSD-16", "fuel_id": fuel_id, "capacity": "20000", "opening_stock": "1000"}).json()
    url = f"/api/tanks/{tank['id']}/dip-chart"
    put = lambda rows: client.put(url, headers=manager, json={"rows": [{"dip_cm": d, "litres": l} for d, l in rows]})  # noqa: E731
    assert put([("0", "0")]).status_code == 422                                  # too short
    assert put([("0", "0"), ("0", "10")]).status_code == 422                     # the same dip twice
    assert put([("0", "100"), ("10", "50")]).status_code == 422                  # litres fall as the dip rises
    assert put([("0", "0"), ("100", "90000")]).status_code == 422                # more than the tank holds
    assert put([("0", "abc"), ("100", "100")]).status_code == 422
    assert put([("0", "0"), ("100", "20000")]).status_code == 200
    assert put([("0", "0"), ("50", "9000"), ("100", "20000")]).status_code == 200
    db = session_factory()
    rows = db.query(TankDipChartPoint).filter_by(tank_id=tank["id"]).all()
    assert len(rows) == 5 and sum(1 for r in rows if r.voided_at is None) == 3   # the first chart is voided, not deleted
    db.close()
    assert len(audit_events(session_factory, "tank_dip_chart_set")) == 2 and audit_chain_ok(session_factory)

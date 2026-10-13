from datetime import date

from api_helpers import audit_chain_ok, audit_events
from test_api_sales import pump  # noqa: F401  (fixture)

TODAY = date.today().isoformat()


def _shift_checks(client, h):
    return client.get(f"/api/checks?day={TODAY}", headers=h).json()


def test_checks_need_a_session_and_the_permission(client, owner, manager, accountant, data_entry, attendant):
    assert client.get("/api/checks", headers={"X-Launch-Secret": client.headers["X-Launch-Secret"]}).status_code == 401
    assert client.get("/api/checks", headers=attendant).status_code == 403
    assert client.get("/api/checks", headers=data_entry).status_code == 403
    for h in (owner, manager, accountant):
        assert client.get("/api/checks", headers=h).status_code == 200
    assert client.post("/api/checks/run", headers=attendant, json={}).status_code == 403
    assert client.get("/api/checks/history?day=" + TODAY, headers=data_entry).status_code == 403
    assert client.get("/api/checks/days", headers=attendant).status_code == 403


def _close_pump(client, h, pump, closing="40.000"):
    aid = client.get(f"/api/shifts/{pump['shift']['id']}/assignments", headers=h).json()[0]["id"]
    r = client.post(f"/api/shift-assignments/{aid}/complete", headers=h, json={"closing_meter": closing})
    assert r.status_code == 200, r.text


def _by_key(body):
    return {r["key"]: r for r in body["results"]}


def test_closing_a_nozzle_runs_the_checks_without_being_asked(client, owner, manager, pump, session_factory):
    assert "shift.litres_match_meters" not in _by_key(_shift_checks(client, owner))  # nothing metered yet
    _close_pump(client, manager, pump)
    body = _shift_checks(client, owner)  # nobody called /checks/run: the save did
    litres = _by_key(body)["shift.litres_match_meters"]
    assert litres["status"] == "pass" and litres["expected"] == "40.000" and litres["actual"] == "40.000"
    assert litres["unit"] == "litres" and litres["links"][0]["route"] == f"/shifts/{pump['shift']['id']}"
    # The cashier has not typed Advance / Final / payment modes yet, so the money does not add up to the 4,000
    # of fuel sold: the report check says so in front of the owner. Everything else on the day is fine.
    assert [r["key"] for r in body["results"] if r["status"] == "fail"] == ["report.shift_total_equals_total_sale"]
    gap = _by_key(body)["report.shift_total_equals_total_sale"]
    assert (gap["expected"], gap["actual"], gap["difference"]) == ("4000.00", "0.00", "-4000.00")
    assert body["summary"]["passed"] >= 1
    assert audit_events(session_factory, "check_recorded") and audit_chain_ok(session_factory)


def test_a_wrong_dip_fails_and_sorts_first_and_history_keeps_it(client, owner, manager, pump, session_factory):
    _close_pump(client, manager, pump)
    tid = pump["tank"]["id"]
    bad = client.post(f"/api/tanks/{tid}/reconciliations", headers=manager, json={"reconciliation_date": TODAY, "physical_stock": "2000.000"})
    assert bad.status_code == 201, bad.text
    body = _shift_checks(client, owner)
    dip = _by_key(body)["tank.dip_matches_book"]
    assert dip["status"] == "fail" and dip["actual"] == "2000.000" and dip["expected"] == "2460.500"
    # the dip also disagrees with the daily report's Total Stock, so two checks name the same problem
    assert body["results"][0]["status"] == "fail" and body["summary"]["failed"] >= 1
    assert {r["key"] for r in body["results"] if r["status"] == "fail"} >= {"tank.dip_matches_book"}
    hist = client.get(f"/api/checks/history?day={TODAY}", headers=owner).json()
    assert len(hist) >= len(body["results"]) and TODAY in client.get("/api/checks/days", headers=owner).json()


def test_explanation_is_recorded_and_status_is_untouched(client, owner, accountant, manager, pump, session_factory):
    _close_pump(client, manager, pump)
    client.post(f"/api/tanks/{pump['tank']['id']}/reconciliations", headers=manager, json={"reconciliation_date": TODAY, "physical_stock": "2000.000"})
    target = _by_key(_shift_checks(client, owner))["tank.dip_matches_book"]
    ok = client.post(f"/api/checks/{target['id']}/explanations", headers=accountant, json={"text": "Dip stick wet"})
    assert ok.status_code == 201
    after = ok.json()
    assert after["status"] == "fail" and after["explanations"][0]["text"] == "Dip stick wet"
    assert after["explanations"][0]["by"] == "accountant1" and after["explanations"][0]["at"]
    assert client.post(f"/api/checks/{target['id']}/explanations", headers=owner, json={"text": "  "}).status_code == 422
    assert client.post(f"/api/checks/{target['id']}/explanations", headers=data_entry_headers(client), json={"text": "x"}).status_code == 403
    assert audit_events(session_factory, "check_explained")
    still = _by_key(_shift_checks(client, owner))["tank.dip_matches_book"]
    assert still["status"] == "fail"  # an explanation never turns a failure into a pass


def data_entry_headers(client):
    from api_helpers import login

    return login(client, "dataentry1")


def test_run_endpoint_recomputes_a_past_day(client, owner, pump):
    r = client.post("/api/checks/run", headers=owner, json={"day": "2020-01-01"})
    assert r.status_code == 200 and r.json()["results"] == []


def test_pump_settings_read_and_owner_only_write(client, owner, manager, data_entry, session_factory):
    rows = client.get("/api/pump-settings", headers=data_entry).json()
    assert {r["key"] for r in rows} >= {"rounding_rule", "add_testing_back", "credit_over_limit"}
    assert next(r for r in rows if r["key"] == "rounding_rule")["value"] == "per_bill"
    ok = client.put("/api/pump-settings/credit_over_limit", headers=owner, json={"value": "block"})
    assert ok.status_code == 200 and ok.json()["value"] == "block"
    assert client.put("/api/pump-settings/credit_over_limit", headers=owner, json={"value": "nope"}).status_code == 422
    assert client.put("/api/pump-settings/credit_over_limit", headers=data_entry, json={"value": "warn"}).status_code == 403
    # the owners' rules are the owners' to change: a manager (who can edit the company profile) cannot
    assert client.put("/api/pump-settings/credit_over_limit", headers=manager, json={"value": "warn"}).status_code == 403
    assert client.get("/api/pump-settings", headers=manager).status_code == 200
    assert audit_events(session_factory, "pump_setting_changed")

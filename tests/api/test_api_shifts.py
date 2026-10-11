from api_helpers import audit_chain_ok, audit_events


def _nozzle(client, h, fuel_id, tank):
    d = client.post("/api/dispensers", headers=h, json={"code": "D1"}).json()
    n = client.post("/api/nozzles", headers=h, json={"code": "N1", "dispenser_id": d["id"], "fuel_id": fuel_id, "tank_id": tank["id"]})
    assert n.status_code == 201, n.text
    return n.json()


def _open(client, h, label="Morning"):
    r = client.post("/api/shifts", headers=h, json={"shift_date": "2026-10-11", "shift_label": label, "notes": "n"})
    assert r.status_code == 201, r.text
    return r.json()


def test_open_list_get_and_validation(client, manager, accountant, attendant, session_factory):
    s = _open(client, manager)
    assert s["status"] == "open" and s["opened_by"] == "manager1" and s["shift_label"] == "Morning"
    assert client.post("/api/shifts", headers=manager, json={"shift_date": "2026-10-11", "shift_label": "  "}).status_code == 422
    assert client.post("/api/shifts", headers=manager, json={"shift_date": "nope", "shift_label": "x"}).status_code == 422
    assert [x["id"] for x in client.get("/api/shifts", headers=accountant).json()] == [s["id"]]
    assert client.get(f"/api/shifts/{s['id']}", headers=accountant).json()["shift_label"] == "Morning"
    assert client.post("/api/shifts", headers=accountant, json={"shift_date": "2026-10-12", "shift_label": "Night"}).status_code == 403
    assert client.get("/api/shifts", headers=attendant).status_code == 403
    assert client.get("/api/shifts/nope", headers=manager).status_code == 404
    assert len(audit_events(session_factory, "shift_opened")) == 1 and audit_chain_ok(session_factory)


def test_assign_complete_close_reopen(client, manager, accountant, fuel_id, tank, employee_id, session_factory):
    nozzle = _nozzle(client, manager, fuel_id, tank)
    # Completing an assignment settles the metered litres as a sale, which needs a priced fuel.
    client.post(f"/api/fuel-prices/{fuel_id}/rate", headers=manager, json={"new_rate_per_liter": "100.00"})
    s = _open(client, manager)
    opts = client.get("/api/shifts/assign-options", headers=manager).json()
    assert opts["nozzles"][0]["label"] == "N1" and opts["employees"][0]["label"].startswith("EMP-0001")
    url = f"/api/shifts/{s['id']}/assignments"
    a = client.post(url, headers=manager, json={"employee_id": employee_id, "nozzle_id": nozzle["id"], "opening_meter": "1000.000"})
    assert a.status_code == 201 and a.json()["status"] == "active" and a.json()["employee"] == "Ravi Kumar"
    aid = a.json()["id"]
    # the same nozzle cannot be assigned twice at once
    assert client.post(url, headers=manager, json={"employee_id": employee_id, "nozzle_id": nozzle["id"], "opening_meter": "1000"}).status_code in (409, 422)
    # cannot close while an assignment is active
    assert client.post(f"/api/shifts/{s['id']}/close", headers=manager, json={}).status_code == 409
    # closing meter below opening is a rule violation
    assert client.post(f"/api/shift-assignments/{aid}/complete", headers=manager, json={"closing_meter": "900"}).status_code in (409, 422)
    done = client.post(f"/api/shift-assignments/{aid}/complete", headers=manager, json={"closing_meter": "1100.500", "testing_volume": "5", "internal_consumption_volume": "2.5"})
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "completed" and done.json()["closing_meter"] == "1100.500" and done.json()["testing_volume"] == "5.000"
    assert len(client.get(url, headers=manager).json()) == 1
    closed = client.post(f"/api/shifts/{s['id']}/close", headers=manager, json={})
    assert closed.status_code == 200 and closed.json()["status"] == "closed"
    # only users with shift.reopen may reopen; a reason is optional
    assert client.post(f"/api/shifts/{s['id']}/reopen", headers=accountant, json={}).status_code == 403
    reopened = client.post(f"/api/shifts/{s['id']}/reopen", headers=manager, json={})
    assert reopened.status_code == 200 and reopened.json()["status"] == "open"
    assert reopened.json()["reopen_reason"] == "No reason given"
    assert audit_chain_ok(session_factory)


def test_cancel_assignment_and_forbidden(client, manager, accountant, fuel_id, tank, employee_id):
    nozzle = _nozzle(client, manager, fuel_id, tank)
    s = _open(client, manager)
    url = f"/api/shifts/{s['id']}/assignments"
    assert client.post(url, headers=accountant, json={"employee_id": employee_id, "nozzle_id": nozzle["id"], "opening_meter": "1"}).status_code == 403
    a = client.post(url, headers=manager, json={"employee_id": employee_id, "nozzle_id": nozzle["id"], "opening_meter": "10"}).json()
    c = client.post(f"/api/shift-assignments/{a['id']}/cancel", headers=manager, json={})
    assert c.status_code == 200 and c.json()["status"] == "cancelled"
    assert client.post("/api/shift-assignments/nope/cancel", headers=manager, json={}).status_code == 404
    floaty = client.post(url, headers=manager, json={"employee_id": employee_id, "nozzle_id": nozzle["id"], "opening_meter": 10.5})
    assert floaty.status_code == 422


def test_my_shift_empty_for_an_unassigned_attendant_and_forbidden_for_others(client, attendant, accountant):
    assert client.get("/api/shifts/mine", headers=attendant).json() is None
    assert client.get("/api/shifts/mine", headers=accountant).status_code == 403

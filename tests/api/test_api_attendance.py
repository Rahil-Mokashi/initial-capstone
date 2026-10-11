from api_helpers import audit_chain_ok, audit_events

DAY = "2026-10-11"


def _mark(client, h, employee_id, status="present", **over):
    return client.post("/api/attendance", headers=h, json={"employee_id": employee_id, "attendance_date": DAY, "status": status, **over})


def test_mark_list_and_duplicate(client, manager, accountant, attendant, employee_id, session_factory):
    r = _mark(client, manager, employee_id)
    assert r.status_code == 201 and r.json()["status"] == "present" and r.json()["employee"] == "Ravi Kumar"
    rows = client.get(f"/api/attendance?date={DAY}", headers=accountant).json()
    assert [x["employee_id"] for x in rows] == [employee_id]
    assert client.get("/api/attendance?date=2026-10-12", headers=accountant).json() == []
    assert _mark(client, manager, employee_id, "absent").status_code in (409, 422)
    assert _mark(client, accountant, employee_id).status_code == 403
    assert client.get(f"/api/attendance?date={DAY}", headers=attendant).status_code == 403
    assert client.get("/api/attendance", headers=manager).status_code == 422
    assert _mark(client, manager, employee_id, "flying").status_code == 422
    assert _mark(client, manager, "nope").status_code == 404
    assert len(audit_events(session_factory, "attendance_marked")) == 1 and audit_chain_ok(session_factory)


def test_correct_with_and_without_reason(client, manager, employee_id, session_factory):
    a = _mark(client, manager, employee_id).json()
    c = client.post(f"/api/attendance/{a['id']}/correct", headers=manager, json={"status": "late", "overtime_minutes": 30, "reason": "came at 10"})
    assert c.status_code == 200 and c.json()["status"] == "late" and c.json()["overtime_minutes"] == 30
    assert c.json()["corrected_at"] and c.json()["correction_reason"] == "came at 10"
    blank = client.post(f"/api/attendance/{a['id']}/correct", headers=manager, json={"status": "present"})
    assert blank.status_code == 200 and blank.json()["correction_reason"] == "No reason given"
    assert client.post(f"/api/attendance/{a['id']}/correct", headers=manager, json={"overtime_minutes": -5}).status_code == 422
    assert client.post("/api/attendance/nope/correct", headers=manager, json={}).status_code == 404
    assert client.get(f"/api/attendance/{a['id']}", headers=manager).json()["status"] == "present"
    assert len(audit_events(session_factory, "attendance_corrected")) == 2 and audit_chain_ok(session_factory)


def test_shift_list_can_be_limited_to_a_day(client, manager):
    for d in ("2026-10-11", "2026-10-12"):
        client.post("/api/shifts", headers=manager, json={"shift_date": d, "shift_label": "Morning"})
    one = client.get("/api/shifts?date_from=2026-10-11&date_to=2026-10-11", headers=manager).json()
    assert [s["shift_date"] for s in one] == ["2026-10-11"]


def test_leave_request_approve_writes_attendance_and_reject_cancel(client, manager, accountant, employee_id, session_factory):
    body = {"employee_id": employee_id, "date_from": "2026-10-20", "date_to": "2026-10-22", "reason": "wedding"}
    r = client.post("/api/leave", headers=manager, json=body)
    assert r.status_code == 201 and r.json()["status"] == "pending"
    lid = r.json()["id"]
    assert client.post("/api/leave", headers=manager, json={**body, "date_from": "2026-10-25"}).status_code == 422
    assert client.post("/api/leave", headers=accountant, json=body).status_code == 403
    ok = client.post(f"/api/leave/{lid}/approve", headers=manager, json={})
    assert ok.status_code == 200 and ok.json()["status"] == "approved" and ok.json()["decided_by"] == "manager1"
    days = client.get("/api/attendance?date=2026-10-21", headers=manager).json()
    assert days and days[0]["status"] == "leave"
    assert client.post(f"/api/leave/{lid}/approve", headers=manager, json={}).status_code == 409
    second = client.post("/api/leave", headers=manager, json={**body, "date_from": "2026-11-01", "date_to": "2026-11-01"}).json()
    rej = client.post(f"/api/leave/{second['id']}/reject", headers=manager, json={})
    assert rej.json()["status"] == "rejected" and rej.json()["decision_reason"] == "No reason given"
    third = client.post("/api/leave", headers=manager, json={**body, "date_from": "2026-12-01", "date_to": "2026-12-01"}).json()
    assert client.post(f"/api/leave/{third['id']}/cancel", headers=manager, json={"reason": "plans changed"}).json()["status"] == "cancelled"
    assert len(client.get("/api/leave", headers=accountant).json()) == 3
    noreason = client.post("/api/leave", headers=manager, json={**body, "date_from": "2026-12-05", "date_to": "2026-12-05", "reason": "  "})
    assert noreason.status_code == 201 and noreason.json()["reason"] == "No reason given"
    assert audit_chain_ok(session_factory)

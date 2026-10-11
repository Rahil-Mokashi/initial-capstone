from datetime import date

import pytest

from api_helpers import audit_chain_ok, audit_events

NEW = {
    "first_name": "Asha",
    "last_name": "Patil",
    "contact_number": "+91 98765 43210",
    "joining_date": "2026-01-15",
    "designation": "Attendant",
    "department": "Forecourt",
}


def _create(client, headers, **over):
    return client.post("/api/employees", headers=headers, json={**NEW, **over})


# ---- read -------------------------------------------------------------------
def test_list_and_get(client, manager, employee_id):
    rows = client.get("/api/employees", headers=manager).json()
    assert [r["employee_code"] for r in rows] == ["EMP-0001"]
    one = client.get(f"/api/employees/{employee_id}", headers=manager).json()
    assert one["first_name"] == "Ravi" and one["status"] == "active" and one["exit_date"] is None


def test_read_permissions(client, accountant, attendant, employee_id):
    assert client.get("/api/employees", headers=accountant).status_code == 200  # view-only role
    denied = client.get("/api/employees", headers=attendant)
    assert denied.status_code == 403 and denied.json()["error"]["details"]["permission"] == "employee.view"
    assert client.get(f"/api/employees/{employee_id}", headers=attendant).status_code == 403


def test_get_unknown_is_404(client, manager):
    assert client.get("/api/employees/nope", headers=manager).status_code == 404


# ---- create -----------------------------------------------------------------
def test_create_assigns_the_next_code_and_audits(client, manager, employee_id, session_factory):
    resp = _create(client, manager)
    assert resp.status_code == 201
    body = resp.json()
    assert body["employee_code"] == "EMP-0002" and body["status"] == "active" and body["first_name"] == "Asha"
    [entry] = audit_events(session_factory, "employee_created")
    assert entry.entity_id == body["id"]
    assert audit_chain_ok(session_factory)


def test_create_403_for_view_only(client, accountant, session_factory):
    assert _create(client, accountant).status_code == 403
    assert audit_events(session_factory, "employee_created") == []


@pytest.mark.parametrize(
    "over",
    [
        {"first_name": "   "},
        {"contact_number": "abc"},
        {"contact_number": "12"},
        {"joining_date": "not-a-date"},
        {"emergency_contact_phone": "x"},
    ],
)
def test_create_422(client, manager, over):
    resp = _create(client, manager, **over)
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "validation_error"


def test_create_rejects_unknown_fields(client, manager):
    assert _create(client, manager, role_id="whatever").status_code == 422


# ---- update -----------------------------------------------------------------
def test_update_changes_only_the_sent_fields(client, manager, employee_id, session_factory):
    resp = client.patch(f"/api/employees/{employee_id}", headers=manager, json={"designation": "Supervisor"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["designation"] == "Supervisor" and body["first_name"] == "Ravi" and body["contact_number"] == "9876543210"
    assert len(audit_events(session_factory, "employee_updated")) == 1
    assert audit_chain_ok(session_factory)


def test_update_403_404_422(client, manager, accountant, employee_id):
    assert client.patch(f"/api/employees/{employee_id}", headers=accountant, json={"designation": "x"}).status_code == 403
    assert client.patch("/api/employees/nope", headers=manager, json={"designation": "x"}).status_code == 404
    assert client.patch(f"/api/employees/{employee_id}", headers=manager, json={"contact_number": "bad!"}).status_code == 422


# ---- status -----------------------------------------------------------------
def test_status_change_needs_a_reason_and_is_audited(client, manager, employee_id, session_factory):
    resp = client.post(
        f"/api/employees/{employee_id}/status", headers=manager, json={"status": "on_leave", "reason": "Family event"}
    )
    assert resp.status_code == 200 and resp.json()["status"] == "on_leave"
    [entry] = audit_events(session_factory, "employee_status_changed")
    assert (entry.old_value, entry.new_value, entry.description) == ("active", "on_leave", "Family event")
    assert audit_chain_ok(session_factory)


def test_status_422_403(client, manager, accountant, employee_id):
    url = f"/api/employees/{employee_id}/status"
    # A blank reason is allowed (owner decision): it is stored as "No reason given".
    assert client.post(url, headers=manager, json={"status": "on_leave", "reason": "   "}).status_code == 200
    assert client.post(url, headers=manager, json={"status": "flying", "reason": "x"}).status_code == 422
    assert client.post(url, headers=accountant, json={"status": "on_leave", "reason": "x"}).status_code == 403


# ---- exit -------------------------------------------------------------------
def test_exit_terminates_and_keeps_the_record(client, manager, employee_id, session_factory):
    resp = client.post(
        f"/api/employees/{employee_id}/exit", headers=manager, json={"exit_date": "2026-09-30", "reason": "Resigned"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "terminated" and body["exit_date"] == "2026-09-30"
    assert len(client.get("/api/employees", headers=manager).json()) == 1  # never deleted
    assert len(audit_events(session_factory, "employee_exit")) == 1
    assert audit_chain_ok(session_factory)


def test_exit_defaults_to_today_like_the_qt_screen(client, manager, employee_id):
    body = client.post(f"/api/employees/{employee_id}/exit", headers=manager, json={"reason": "Left"}).json()
    assert body["exit_date"] == date.today().isoformat()


def test_exit_before_joining_is_a_rule_error(client, manager, employee_id):
    resp = client.post(
        f"/api/employees/{employee_id}/exit", headers=manager, json={"exit_date": "2020-01-01", "reason": "x"}
    )
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "rule_violation"


def test_exit_403_422(client, accountant, manager, employee_id):
    url = f"/api/employees/{employee_id}/exit"
    assert client.post(url, headers=accountant, json={"reason": "x"}).status_code == 403
    assert client.post(url, headers=manager, json={"exit_date": "not-a-date"}).status_code == 422


# ---- documents --------------------------------------------------------------
def test_document_add_list_remove(client, manager, accountant, employee_id, session_factory):
    base = f"/api/employees/{employee_id}/documents"
    path = "C:\\docs\\id.pdf"
    added = client.post(base, headers=manager, json={"document_type": "ID Proof", "file_reference": path})
    assert added.status_code == 201
    doc = added.json()
    assert doc["document_type"] == "ID Proof" and doc["file_reference"] == path
    assert [d["id"] for d in client.get(base, headers=accountant).json()] == [doc["id"]]

    removed = client.post(
        f"/api/employees/documents/{doc['id']}/remove", headers=manager, json={"reason": "Uploaded by mistake"}
    )
    assert removed.status_code == 200
    assert client.get(base, headers=manager).json() == []  # hidden, never destroyed
    assert len(audit_events(session_factory, "employee_document_added")) == 1
    assert len(audit_events(session_factory, "employee_document_removed")) == 1
    assert audit_chain_ok(session_factory)


def test_document_403_404_422(client, manager, accountant, attendant, employee_id):
    base = f"/api/employees/{employee_id}/documents"
    body = {"document_type": "Photo", "file_reference": "p.jpg"}
    assert client.post(base, headers=accountant, json=body).status_code == 403
    assert client.get(base, headers=attendant).status_code == 403
    assert client.post("/api/employees/nope/documents", headers=manager, json=body).status_code == 404
    assert client.post(base, headers=manager, json={"document_type": " ", "file_reference": "x"}).status_code == 422
    remove = "/api/employees/documents/nope/remove"
    assert client.post(remove, headers=manager, json={"reason": "x"}).status_code == 404
    assert client.post(remove, headers=accountant, json={"reason": "x"}).status_code == 403
    assert client.post(remove, headers=manager, json={}).status_code == 404  # reason is optional; the id is unknown

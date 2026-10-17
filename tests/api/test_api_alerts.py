"""Alerts that can be dealt with: shown once with a count, acknowledged with a reason (who and when kept), a cash shortage marked
against one of the people who worked the shift (which resolves it), and nothing here changes what a check says."""

from api_helpers import audit_chain_ok, audit_events
from test_api_reconciliation import _cash_sale, _expected
from test_api_sales import pump  # noqa: F401  (fixture)


def _short_alert(client, h):
    return next((a for a in client.get("/api/alerts", headers=h).json()["notifications"] if a["category"] == "cash_shortage"), None)


def _book_a_short_reconciliation(client, manager, pump, declared="900.00"):
    _cash_sale(client, manager, pump, "1000.00")
    sid = pump["shift"]["id"]
    cash = next(e for e in _expected(client, manager, sid) if e["tender"] == "Cash")
    r = client.post("/api/reconciliation", headers=manager, json={"shift_id": sid, "declared_amounts": {cash["tender_id"]: declared}})
    assert r.status_code == 201, r.text


def test_a_cash_shortage_alert_names_who_worked_the_shift_and_marking_it_resolves_it(client, manager, owner, pump, employee_id, session_factory):
    _book_a_short_reconciliation(client, manager, pump)
    alert = _short_alert(client, owner)
    assert alert and alert["shortage"]["employees"][0]["id"] == employee_id
    assert alert["shortage"]["suggested_employee_id"] == employee_id  # only one person worked it
    # only people who worked that shift can be named
    stranger = "00000000-0000-0000-0000-000000000000"
    assert client.post("/api/alerts/shortage", headers=manager, json={"line_id": alert["shortage"]["line_id"], "employee_id": stranger}).status_code == 409
    done = client.post("/api/alerts/shortage", headers=manager, json={"line_id": alert["shortage"]["line_id"], "employee_id": employee_id})
    assert done.status_code == 204, done.text
    assert _short_alert(client, owner) is None  # resolved
    shortages = client.get("/api/shortages", headers=manager).json()
    assert len(shortages) == 1 and shortages[0]["outstanding"] == "100.00"
    assert audit_events(session_factory, "employee_cash_shortage_recorded") and audit_chain_ok(session_factory)


def test_acknowledging_needs_a_reason_keeps_who_and_when_and_hides_it_for_the_day(client, manager, owner, accountant, attendant, pump, session_factory):
    _book_a_short_reconciliation(client, manager, pump)
    key = _short_alert(client, owner)["key"]
    assert client.post("/api/alerts/acknowledge", headers=owner, json={"key": key, "reason": "  "}).status_code == 422
    assert client.post("/api/alerts/acknowledge", headers=attendant, json={"key": key, "reason": "x"}).status_code == 403
    before = client.get(f"/api/checks?day=2000-01-01", headers=owner).json()
    ok = client.post("/api/alerts/acknowledge", headers=owner, json={"key": key, "reason": "Known: the attendant will pay it back on Friday"})
    assert ok.status_code == 204, ok.text
    assert _short_alert(client, owner) is None
    assert audit_events(session_factory, "alert_acknowledged")
    from app.models.alert_acknowledgement import AlertAcknowledgement

    db = session_factory()
    row = db.query(AlertAcknowledgement).one()
    assert row.alert_key == key and "Friday" in row.reason and row.acknowledged_by_id and row.acknowledged_at
    db.close()
    assert client.post("/api/alerts/acknowledge", headers=owner, json={"key": key, "reason": "again"}).status_code == 404  # no longer active
    assert client.get(f"/api/checks?day=2000-01-01", headers=owner).json() == before  # acknowledging never touches a check


def test_the_same_alert_about_the_same_record_shows_once_with_a_count(client, owner, monkeypatch):
    from app.core.constants import NotificationCategory, NotificationSeverity
    from app.services.notification_service import Notification, NotificationService, NotificationSummary

    same = Notification(NotificationCategory.OUTSTANDING_CREDIT, NotificationSeverity.WARNING, "ACME owes 5,000.00", "d", entity_id="c1")
    other = Notification(NotificationCategory.OUTSTANDING_CREDIT, NotificationSeverity.WARNING, "ACME owes 5,000.00", "d", entity_id="c2")
    monkeypatch.setattr(NotificationService, "get_notifications", lambda self, actor: NotificationSummary([same, same, same, other]))
    body = client.get("/api/alerts", headers=owner).json()
    assert body["total"] == 2
    assert sorted(a["count"] for a in body["notifications"]) == [1, 3]


def test_the_employee_page_data_shows_what_is_owed_and_what_was_paid_back(client, manager, pump, employee_id):
    _book_a_short_reconciliation(client, manager, pump)
    alert = _short_alert(client, manager)
    assert client.post("/api/alerts/shortage", headers=manager, json={"line_id": alert["shortage"]["line_id"], "employee_id": employee_id}).status_code == 204
    rows = client.get(f"/api/employees/{employee_id}/shortages", headers=manager).json()
    assert len(rows) == 1 and rows[0]["owed"] == "100.00" and rows[0]["status"] == "Owed" and rows[0]["recoveries"] == []
    sid = pump["shift"]["id"]
    assert client.post("/api/cash-book/movements", headers=manager, json={"shift_id": sid, "advance_amount": "0", "final_amount": "900"}).status_code == 201
    paid = client.post("/api/shortages/recoveries", headers=manager, json={"employee_cash_shortage_id": rows[0]["id"], "shift_id": sid, "amount": "40.00", "notes": "returned"})
    assert paid.status_code == 201, paid.text
    row = client.get(f"/api/employees/{employee_id}/shortages", headers=manager).json()[0]
    assert row["owed"] == "60.00" and row["recovered"] == "40.00" and row["recoveries"][0]["amount"] == "40.00"


def test_a_day_with_a_reconciliation_still_gets_its_checks(client, manager, owner, pump):
    """The 'declared equals expected' check multiplied a Decimal by a float and failed, which silently stopped every check on such a day."""
    import logging
    from datetime import date

    _book_a_short_reconciliation(client, manager, pump)
    ran = client.post("/api/checks/run", headers=owner, json={"day": date.today().isoformat()})
    assert ran.status_code == 200, ran.text
    keys = {r["key"] for r in client.get(f"/api/checks?day={date.today().isoformat()}", headers=owner).json()["results"]}
    assert "shift.declared_matches_expected" in keys

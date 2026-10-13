"""Staff facts (owners and the accountant only; facts, not a score) and the owner's daily digest with per-owner reviewed marks."""

from datetime import date

from api_helpers import audit_chain_ok, audit_events
from pump_day import TODAY
from test_api_close_desk import _body, _modes, _setup
from test_api_reconciliation import _cash_sale, _expected, pump  # noqa: F401  (pump is a fixture)

DAY = "2026-10-11"


def _report(client, h, **q):
    return client.get("/api/reports/staff_facts", headers=h, params=q)


def test_only_owners_and_the_accountant_see_staff_facts(client, owner, accountant, manager, data_entry, attendant):
    for who in (owner, accountant):
        keys = [r["key"] for r in client.get("/api/reports", headers=who).json()["reports"]]
        assert "staff_facts" in keys and _report(client, who).status_code == 200
    for who in (manager, data_entry, attendant):
        keys = [r["key"] for r in client.get("/api/reports", headers=who).json()["reports"]]
        assert "staff_facts" not in keys and _report(client, who).status_code == 403


def test_facts_are_counts_and_amounts_with_no_score_and_no_ranking(client, owner, accountant, manager, employee_id, db):
    # one record per day (a person is marked once a day)
    for n, (status, extra) in enumerate((("present", {}), ("present", {}), ("late", {"overtime_minutes": 90}), ("absent", {})), start=1):
        r = client.post("/api/attendance", headers=manager, json={"employee_id": employee_id, "attendance_date": f"2026-10-{n:02d}", "status": status, **extra})
        assert r.status_code == 201, r.text
    report = _report(client, accountant, date_from="2026-10-01", date_to="2026-10-31").json()
    assert "not a score" in report["title"]
    row = dict(zip(report["headers"], report["rows"][0]))
    assert (row["Code"], row["Name"], row["Days present"], row["Late"], row["Absent"], row["Overtime (hours)"]) == ("EMP-0001", "Ravi Kumar", "2", "1", "1", "1.5")
    assert "Rank" not in report["headers"] and "Score" not in report["headers"] and "Rating" not in report["headers"]
    # a period with nothing on record for anybody is an empty list, not a list of zeros
    assert _report(client, owner, date_from="2025-01-01", date_to="2025-01-31").json()["rows"] == []
    # and it can be exported like every other report
    assert client.get("/api/reports/staff_facts/export.xlsx", headers=accountant).status_code == 200


def test_the_shift_entry_stand_ins_are_not_people_in_the_facts(client, data_entry, manager, owner, session_factory):
    nozzle, shift, _ = _setup(client, manager)
    modes = _modes(client, data_entry, shift["id"])
    client.post(f"/api/close-shift/{shift['id']}", headers=data_entry, json=_body(nozzle, modes))
    client.post("/api/attendance", headers=manager, json={"employee_id": client.get("/api/employees", headers=manager).json()[0]["id"], "attendance_date": TODAY, "status": "present"})
    rows = _report(client, owner).json()["rows"]
    assert all(not r[0].startswith("NOZZLE-") for r in rows)


def test_a_shortage_booked_against_a_person_shows_as_a_fact(client, owner, manager, pump, employee_id):  # noqa: F811
    _cash_sale(client, manager, pump, "1000.00")
    sid = pump["shift"]["id"]
    cash = next(e for e in _expected(client, manager, sid) if e["tender"] == "Cash")
    rid = client.post("/api/reconciliation", headers=manager, json={"shift_id": sid, "declared_amounts": {cash["tender_id"]: "900.00"}}).json()["id"]
    client.post(f"/api/reconciliation/{rid}/approve", headers=manager, json={"remarks": "seen"})
    line = client.get("/api/shortages/options", headers=manager).json()["unbooked_lines"][0]["id"]
    client.post("/api/shortages", headers=manager, json={"shift_reconciliation_line_id": line, "employee_id": employee_id})
    client.post("/api/attendance", headers=manager, json={"employee_id": employee_id, "attendance_date": TODAY, "status": "present"})
    report = _report(client, owner).json()
    row = dict(zip(report["headers"], report["rows"][0]))
    assert (row["Cash shortages"], row["Shortage amount"], row["Paid back"], row["Still owed"]) == ("1", "100.00", "0.00", "100.00")


# ---- the daily digest ---------------------------------------------------------------------------------------------------
def test_the_digest_says_how_the_day_went_in_the_close_desk_s_own_figures(client, owner, data_entry, manager, accountant):
    nozzle, shift, _ = _setup(client, manager)
    modes = _modes(client, data_entry, shift["id"])
    client.post(f"/api/close-shift/{shift['id']}", headers=data_entry, json=_body(nozzle, modes))  # 50,000 sold, 49,000 collected: short 1,000
    d = client.get(f"/api/digest?day={TODAY}", headers=owner).json()
    assert d["day"] == TODAY and d["total_sale"] == "50000.00" and d["litres_sold"] == "500.000"
    assert [(s["label"], s["total_sale"], s["collected"], s["difference"], s["status"], s["entry_status"]) for s in d["shifts"]] == [
        ("Morning", "50000.00", "49000.00", "1000.00", "short", "entered")]
    assert d["waiting"] == {"entered": 1}
    assert d["checks_total"] > 0 and any("not yet verified" in c["sentence"] for c in d["checks_to_look_at"])
    # with no day given it opens on the latest day that has a shift
    assert client.get("/api/digest", headers=owner).json()["day"] == TODAY


def test_each_owner_marks_a_day_reviewed_for_themselves_and_the_first_mark_stays(client, owner, admin, data_entry, manager, session_factory):
    _setup(client, manager)
    first = client.post("/api/digest/review", headers=owner, json={"day": TODAY}).json()
    assert first["reviewed_by_me"] and [r["by"] for r in first["reviewed"]] == ["owner1"]
    again = client.post("/api/digest/review", headers=owner, json={"day": TODAY}).json()
    assert again["reviewed"][0]["at"] == first["reviewed"][0]["at"]
    other = client.get(f"/api/digest?day={TODAY}", headers=admin).json()
    assert other["reviewed_by_me"] is False and [r["by"] for r in other["reviewed"]] == ["owner1"]  # an owner sees who has looked
    assert len(audit_events(session_factory, "digest_reviewed")) == 1 and audit_chain_ok(session_factory)


def test_the_digest_is_for_owners_only(client, accountant, manager, data_entry, attendant):
    for who in (accountant, manager, data_entry, attendant):
        assert client.get("/api/digest", headers=who).status_code == 403
        assert client.post("/api/digest/review", headers=who, json={"day": TODAY}).status_code == 403

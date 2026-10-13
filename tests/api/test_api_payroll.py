"""Payroll v1: salary setup, advances, the monthly register, owner approval before payment, cash or bank payment,
payslips and the tallies shown as checks. Synthetic employees only."""

from datetime import date
from decimal import Decimal

import pytest

from api_helpers import audit_chain_ok, audit_events
from app.models.attendance import Attendance
from app.core.money import money
from app.models.employee import Employee

D = Decimal
import calendar

_t = date.today()
_py, _pm = (_t.year, _t.month - 1) if _t.month > 1 else (_t.year - 1, 12)
MONTH = f"{_py}-{_pm:02d}"
N = calendar.monthrange(_py, _pm)[1]  # days in the month being paid
PAID = N - 2  # n-4 present + 1 late + 2 half days
GROSS1 = money(D("30000") * PAID / N)



@pytest.fixture()
def staff(db):
    e1 = Employee(employee_code="E1", first_name="Asha", last_name="Patil", contact_number="9", joining_date=date(2026, 1, 1))
    e2 = Employee(employee_code="E2", first_name="Ravi", last_name="Kumar", contact_number="9", joining_date=date(2026, 1, 1))
    db.add_all([e1, e2])
    db.commit()

    def mark(emp, day_no, status):
        db.add(Attendance(employee_id=emp.id, attendance_date=date(_py, _pm, day_no), status=status))

    for d in range(1, N - 3):
        mark(e1, d, "present")
    mark(e1, N - 3, "half_day")
    mark(e1, N - 2, "half_day")
    mark(e1, N - 1, "late")
    mark(e1, N, "absent")  # n-4 present + 1 late + 2 half days = n-2 days paid
    for d in range(1, N + 1):
        mark(e2, d, "present")
    db.commit()
    return {"e1": e1.id, "e2": e2.id}


def _salaries(client, h, staff):
    assert client.put(f"/api/payroll/salaries/{staff['e1']}", headers=h, json={"monthly_salary": "30000.00", "effective_from": "2026-01-01"}).status_code == 200
    assert client.put(f"/api/payroll/salaries/{staff['e2']}", headers=h, json={"monthly_salary": "20000.00", "effective_from": "2026-01-01"}).status_code == 200


def _prepare(client, h):
    r = client.post("/api/payroll/runs", headers=h, json={"month": MONTH})
    assert r.status_code == 201, r.text
    return r.json()


def _lines(reg):
    return {l["employee_name"]: l for l in reg["lines"]}


def test_who_may_do_what(client, staff, accountant, owner, manager, attendant, data_entry):
    for h in (manager, attendant, data_entry):
        assert client.get("/api/payroll/salaries", headers=h).status_code == 403
    assert client.get("/api/payroll/salaries", headers=accountant).status_code == 200
    assert client.put(f"/api/payroll/salaries/{staff['e1']}", headers=manager, json={"monthly_salary": "1.00", "effective_from": "2026-01-01"}).status_code == 403
    assert client.put(f"/api/payroll/salaries/{staff['e1']}", headers=accountant, json={"monthly_salary": "0.00", "effective_from": "2026-01-01"}).status_code == 422
    assert client.get("/api/payroll/salaries", headers={"X-Launch-Secret": client.headers["X-Launch-Secret"]}).status_code == 401


def test_salary_is_prorated_by_days_present_from_the_attendance_records(client, staff, accountant):
    _salaries(client, accountant, staff)
    reg = _prepare(client, accountant)
    lines = _lines(reg)
    asha, ravi = lines["Asha Patil"], lines["Ravi Kumar"]
    assert (asha["days_in_month"], asha["days_present"], asha["paid_days"]) == (N, f"{PAID}.0", f"{PAID}.0")
    assert asha["gross"] == str(GROSS1) and asha["net"] == str(GROSS1)  # 30,000 x days paid / days in the month
    assert ravi["gross"] == "20000.00"
    assert (reg["status"], reg["gross"], reg["net"]) == ("draft", str(GROSS1 + D("20000.00")), str(GROSS1 + D("20000.00")))
    assert client.post("/api/payroll/runs", headers=accountant, json={"month": MONTH}).status_code == 409  # one register per month
    assert client.post("/api/payroll/runs", headers=accountant, json={"month": "2026-13"}).status_code == 422


def test_leave_and_holidays_count_only_when_the_owner_says_so(client, staff, db, accountant, owner):
    _salaries(client, accountant, staff)
    db.query(Attendance).filter_by(employee_id=staff["e1"], attendance_date=date(_py, _pm, N)).update({"status": "leave"})
    db.commit()
    assert _lines(_prepare(client, accountant))["Asha Patil"]["paid_days"] == f"{PAID}.0"  # leave is not paid by default (U-04)


def test_advances_deductions_and_their_limits(client, staff, accountant, owner):
    _salaries(client, accountant, staff)
    adv = client.post("/api/payroll/advances", headers=accountant, json={"employee_id": staff["e1"], "amount": "5000.00", "given_on": "2026-08-20", "method": "cash", "note": "festival"})
    assert adv.status_code == 201
    assert client.post("/api/payroll/advances", headers=accountant, json={"employee_id": staff["e1"], "amount": "0", "given_on": "2026-08-20"}).status_code == 422
    reg = _prepare(client, accountant)
    asha = _lines(reg)["Asha Patil"]
    assert asha["advance_outstanding"] == "5000.00"
    ok = client.put(f"/api/payroll/lines/{asha['id']}/deductions", headers=accountant, json={"advance": "2000.00", "shortage": "0", "other": "100.00", "other_note": "uniform"})
    assert ok.status_code == 200
    assert client.put(f"/api/payroll/lines/{asha['id']}/deductions", headers=accountant, json={"advance": "6000.00"}).status_code == 422  # only 5,000 was given
    assert client.put(f"/api/payroll/lines/{asha['id']}/deductions", headers=accountant, json={"shortage": "10.00"}).status_code == 422  # no cash shortage on record
    assert client.put(f"/api/payroll/lines/{asha['id']}/deductions", headers=accountant, json={"other": "99999.00"}).status_code == 422  # more than the salary earned
    again = client.get(f"/api/payroll/register/{MONTH}", headers=accountant).json()
    line = _lines(again)["Asha Patil"]
    assert (line["gross"], line["advance_deduction"], line["other_deduction"], line["net"]) == (str(GROSS1), "2000.00", "100.00", str(GROSS1 - D("2100.00")))
    assert (again["gross"], again["advance"], again["other"], again["net"]) == (str(GROSS1 + D("20000.00")), "2000.00", "100.00", str(GROSS1 + D("20000.00") - D("2100.00")))


def test_nobody_is_paid_until_an_owner_approves_and_approval_locks_the_deductions(client, staff, accountant, owner, manager):
    _salaries(client, accountant, staff)
    reg = _prepare(client, accountant)
    asha = _lines(reg)["Asha Patil"]
    pay = {"method": "cash", "paid_on": "2026-10-01"}
    assert client.post(f"/api/payroll/lines/{asha['id']}/pay", headers=accountant, json=pay).status_code == 409  # not approved yet
    assert client.post(f"/api/payroll/runs/{reg['run_id']}/approve", headers=accountant).status_code == 403  # accountants prepare, owners approve
    assert client.post(f"/api/payroll/runs/{reg['run_id']}/approve", headers=manager).status_code == 403
    done = client.post(f"/api/payroll/runs/{reg['run_id']}/approve", headers=owner)
    assert done.status_code == 200
    approved = client.get(f"/api/payroll/register/{MONTH}", headers=accountant).json()
    assert approved["status"] == "approved" and approved["approved_by"] == "owner1" and approved["approved_at"]
    assert client.put(f"/api/payroll/lines/{asha['id']}/deductions", headers=accountant, json={"other": "1.00"}).status_code == 409
    assert client.post(f"/api/payroll/runs/{reg['run_id']}/approve", headers=owner).status_code == 409


def test_paying_in_cash_or_from_the_bank_and_the_month_closes_when_everyone_is_paid(client, staff, accountant, owner, session_factory):
    _salaries(client, accountant, staff)
    reg = _prepare(client, accountant)
    client.post(f"/api/payroll/runs/{reg['run_id']}/approve", headers=owner)
    asha, ravi = _lines(reg)["Asha Patil"], _lines(reg)["Ravi Kumar"]
    bank = client.post("/api/bank/accounts", headers=accountant, json={"name": "Salary Bank", "modes": ["payroll"]}).json()
    assert client.post(f"/api/payroll/lines/{ravi['id']}/pay", headers=accountant, json={"method": "bank", "paid_on": "2026-10-01"}).status_code == 422  # which account?
    p1 = client.post(f"/api/payroll/lines/{asha['id']}/pay", headers=accountant, json={"method": "cash", "paid_on": "2026-10-01"})
    assert p1.status_code == 201 and p1.json()["amount"] == str(GROSS1)
    assert client.post(f"/api/payroll/lines/{asha['id']}/pay", headers=accountant, json={"method": "cash", "paid_on": "2026-10-01"}).status_code == 409  # once
    assert client.get(f"/api/payroll/register/{MONTH}", headers=accountant).json()["status"] == "approved"  # one still to pay
    p2 = client.post(f"/api/payroll/lines/{ravi['id']}/pay", headers=accountant, json={"method": "bank", "paid_on": "2026-10-01", "bank_account_id": bank["id"], "reference": "NEFT-1"})
    assert p2.status_code == 201
    # a salary paid from the bank shows up among the bank's expected payments, so the owner can match it to the statement
    exp = client.get("/api/bank/expected?date_from=2020-01-01&date_to=2099-01-01", headers=accountant).json()
    assert [(e["label"], e["amount"]) for e in exp if e["mode"] == "payroll"] == [("Salaries", "20000.00")]
    assert "Salary Ravi Kumar" in [e["description"] for e in exp][0]
    final = client.get(f"/api/payroll/register/{MONTH}", headers=accountant).json()
    assert final["status"] == "paid" and final["paid"] == str(GROSS1 + D("20000.00"))
    # undoing a payment needs a reason and re-opens the month
    undo = client.post(f"/api/payroll/payments/{p1.json()['id']}/void", headers=accountant, json={"reason": "paid the wrong person"})
    assert undo.status_code == 200
    assert client.get(f"/api/payroll/register/{MONTH}", headers=accountant).json()["status"] == "approved"
    for event in ("payroll_prepared", "payroll_approved", "salary_paid", "salary_payment_voided", "salary_set"):
        assert audit_events(session_factory, event), event
    assert audit_chain_ok(session_factory)


def test_the_tallies_are_checks_the_owners_can_see(client, staff, accountant, owner):
    _salaries(client, accountant, staff)
    client.post("/api/payroll/advances", headers=accountant, json={"employee_id": staff["e1"], "amount": "5000.00", "given_on": "2026-08-20"})
    reg = _prepare(client, accountant)
    asha = _lines(reg)["Asha Patil"]
    client.put(f"/api/payroll/lines/{asha['id']}/deductions", headers=accountant, json={"advance": "2000.00"})
    client.post(f"/api/payroll/runs/{reg['run_id']}/approve", headers=owner)
    for l in reg["lines"]:
        client.post(f"/api/payroll/lines/{l['id']}/pay", headers=accountant, json={"method": "cash", "paid_on": "2026-10-01"})
    day = date.today().isoformat()
    # payroll checks run for the current and the previous month's register, filed under the day they ran
    client.post("/api/checks/run", headers=owner, json={"day": day})
    results = client.get(f"/api/checks?day={day}", headers=owner).json()["results"]
    keys = {}
    for r in results:
        keys.setdefault(r["key"], []).append(r)
    for key in ("payroll.line_net_adds_up", "payroll.register_total_equals_lines", "payroll.payments_equal_register",
                "payroll.paid_only_after_approval", "payroll.advances_recovered_not_more_than_given", "payroll.days_within_month"):
        assert key in keys and all(r["status"] == "pass" for r in keys[key]), key
    adv = next(r for r in keys["payroll.advances_recovered_not_more_than_given"] if "Asha" in r["sentence"])
    assert "given 5000.00, recovered 2000.00, still outstanding 3000.00" in adv["sentence"]
    assert all(r["area"] == "Payroll" for k in keys if k.startswith("payroll.") for r in keys[k])


def test_payslip_for_one_employee_and_month(client, staff, accountant, owner):
    _salaries(client, accountant, staff)
    reg = _prepare(client, accountant)
    asha = _lines(reg)["Asha Patil"]
    slip = client.get(f"/api/payroll/lines/{asha['id']}/payslip", headers=accountant).json()
    assert slip["title"] == f"Payslip - Asha Patil - {MONTH}"
    assert ["Net pay", "", str(GROSS1)] in slip["rows"] and ["Days paid for", f"{PAID}.0", ""] in slip["rows"]
    pdf = client.get(f"/api/payroll/lines/{asha['id']}/payslip.pdf", headers=accountant)
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"
    assert client.get(f"/api/payroll/lines/{asha['id']}/payslip", headers={"X-Launch-Secret": client.headers["X-Launch-Secret"]}).status_code == 401

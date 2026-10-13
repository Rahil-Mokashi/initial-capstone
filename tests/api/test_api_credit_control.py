"""Credit control: history, ageing, the limit at the moment of sale with an owner override, approvals,
recovery follow-ups and statements. Synthetic customers only."""

from datetime import date, timedelta
from decimal import Decimal

from api_helpers import PASSWORD, audit_chain_ok, audit_events
from test_api_daily_report import day  # noqa: F401  (fixture)
from test_api_sales import pump  # noqa: F401  (fixture)

D = Decimal
TODAY = date.today()


def _customer(client, h, name="ACME"):
    return client.post("/api/customers", headers=h, json={"name": name}).json()


def _account(client, h, c, limit="10000.00", days=30):
    r = client.post("/api/credit/accounts", headers=h, json={"customer_id": c["id"], "credit_limit": limit, "payment_due_days": days})
    assert r.status_code == 201, r.text
    return r.json()


def _sale(client, h, pump, c, qty="10.000", **extra):
    body = {"shift_id": pump["shift"]["id"], "nozzle_id": pump["nozzle"]["id"], "employee_id": pump["employee_id"],
            "quantity": qty, "payment_method": "credit", "customer_id": c["id"], **extra}
    return client.post("/api/sales", headers=h, json=body)


def _pay(client, h, c, amount):
    r = client.post("/api/credit/payments", headers=h, json={"customer_id": c["id"], "amount": amount, "payment_method": "cash"})
    assert r.status_code == 201, r.text


def _bowser_bill(client, h, c, no, days_ago, qty="100.000", rate="90.00", transport="0.00", **extra):
    r = client.post("/api/bowser/bills", headers=h, json={
        "bill_no": no, "bill_date": (TODAY - timedelta(days=days_ago)).isoformat(), "customer_id": c["id"],
        "quantity": qty, "rate": rate, "transport": transport, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _detail(client, h, c):
    r = client.get(f"/api/credit/customers/{c['id']}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _owner_id(client, h):
    return next(a["id"] for a in client.get("/api/credit/approvers", headers=h).json() if a["name"].startswith("Owner1"))


# ---------------------------------------------------------------------------- history and ageing
def test_history_shows_bills_payments_balance_and_the_rest(client, manager, pump):
    c = _customer(client, manager)
    _account(client, manager, c)
    for _ in range(3):
        assert _sale(client, manager, pump, c).status_code == 201  # 10 L x 100 = 1,000.00 each
    _pay(client, manager, c, "2500.00")
    d = _detail(client, manager, c)
    assert D(d["balance"]) == D("500.00") and D(d["total_billed"]) == D("3000.00") and D(d["total_paid"]) == D("2500.00")
    # a payment covering several bills clears the oldest first; the third is part paid
    assert sorted(D(b["outstanding"]) for b in d["bills"]) == [D("0"), D("0"), D("500.00")]
    assert d["oldest_unpaid"]["outstanding"] == "500.00" and D(d["available"]) == D("9500.00")
    assert D(d["largest_outstanding_ever"]) == D("3000.00") and d["buckets"]["0-30"] == "500.00"
    assert d["average_days_to_pay"] == "0.0" and d["overdue"] is False and len(d["payments"]) == 1


def test_bowser_bills_join_the_same_history_with_transport(client, manager, pump):
    c = _customer(client, manager, "Beta Concrete")
    _account(client, manager, c, limit="50000.00")
    _bowser_bill(client, manager, c, "B1", 5, qty="100.000", rate="90.00", transport="500.00", vehicle_no="MH14XX0001", slip_no="S-7")
    assert _sale(client, manager, pump, c).status_code == 201
    d = _detail(client, manager, c)
    kinds = {b["kind"]: b for b in d["bills"]}
    assert D(kinds["bowser"]["amount"]) == D("9500.00") and kinds["bowser"]["vehicle_no"] == "MH14XX0001" and kinds["bowser"]["slip_no"] == "S-7"
    assert D(d["balance"]) == D("10500.00")


def test_ageing_buckets_totals_and_oldest_unpaid(client, manager, accountant, pump):
    c1, c2 = _customer(client, manager, "Old Debtor"), _customer(client, manager, "Newer Debtor")
    for c in (c1, c2):
        _account(client, manager, c, limit="900000.00")
    _bowser_bill(client, manager, c1, "O1", 100, qty="10.000", rate="100.00")   # 1,000 at 100 days: 90+
    _bowser_bill(client, manager, c1, "O2", 45, qty="20.000", rate="100.00")    # 2,000 at 45 days: 31-60
    _bowser_bill(client, manager, c2, "N1", 70, qty="30.000", rate="100.00")    # 3,000 at 70 days: 61-90
    _bowser_bill(client, manager, c2, "N2", 3, qty="40.000", rate="100.00")     # 4,000 at 3 days: 0-30
    _pay(client, manager, c1, "400.00")                                         # takes 400 off the oldest bill
    a = client.get("/api/credit/ageing", headers=accountant).json()
    assert a["bucket_names"] == ["0-30", "31-60", "61-90", "90+"]
    assert a["totals"] == {"0-30": "4000.00", "31-60": "2000.00", "61-90": "3000.00", "90+": "600.00"}
    assert D(a["total_balance"]) == D("9600.00")
    rows = {r["name"]: r for r in a["rows"]}
    assert rows["Old Debtor"]["oldest_unpaid_ref"] == "O1" and rows["Old Debtor"]["oldest_unpaid_age"] == 100
    assert rows["Old Debtor"]["buckets"]["90+"] == "600.00" and rows["Old Debtor"]["overdue"] is True
    assert a["rows"][0]["name"] == "Old Debtor"  # oldest debt first


def test_the_internal_bowser_account_is_not_chased(client, day, manager):
    ageing = client.get("/api/credit/ageing", headers=manager).json()
    assert ageing["rows"] and all(r["name"] != "Stock Transfer (Bouser)" for r in ageing["rows"])
    customers = client.get("/api/credit/customers", headers=manager).json()
    assert all(r["name"] != "Stock Transfer (Bouser)" for r in customers)
    # ...but the day's real credit customers are: ACME (shift credit) and Beta (bowser bills)
    names = {r["name"]: r for r in ageing["rows"]}
    assert D(names["ACME Traders"]["balance"]) == D("11000.00")  # 2,000 + 9,000 of credit sales
    assert D(names["Beta Concrete"]["balance"]) == D("39500.00")


# ---------------------------------------------------------------------------- the limit at the moment of sale
def test_limit_check_shows_balance_limit_and_what_the_bill_would_make_it(client, manager, data_entry, pump):
    c = _customer(client, manager)
    _account(client, manager, c, limit="2000.00")
    _sale(client, manager, pump, c, qty="15.000")  # 1,500
    r = client.get(f"/api/credit/check?customer_id={c['id']}&amount=600.00", headers=data_entry).json()
    assert (r["outstanding"], r["credit_limit"], r["would_become"], r["available"]) == ("1500.00", "2000.00", "2100.00", "500.00")
    assert r["over_limit"] is True and r["mode"] == "warn" and r["problem"] is None
    ok = client.get(f"/api/credit/check?customer_id={c['id']}&amount=400.00", headers=data_entry).json()
    assert ok["over_limit"] is False


def test_over_the_limit_is_stopped_with_the_figures_then_allowed_by_an_owner_and_recorded(client, manager, owner, pump, session_factory):
    c = _customer(client, manager)
    _account(client, manager, c, limit="2000.00")
    assert _sale(client, manager, pump, c, qty="15.000").status_code == 201
    stopped = _sale(client, manager, pump, c, qty="6.000")  # would make 2,100
    assert stopped.status_code == 409
    err = stopped.json()["error"]
    assert err["code"] == "credit_limit_exceeded" and err["details"]["can_override"] is True
    assert (err["details"]["outstanding"], err["details"]["credit_limit"], err["details"]["would_become"]) == ("1500.00", "2000.00", "2100.00")
    owner_id = _owner_id(client, manager)
    # a wrong password, then someone who is not an owner: refused, nothing is sold
    assert _sale(client, manager, pump, c, qty="6.000", credit_override={"approver_id": owner_id, "credential": "wrong", "reason": "x"}).status_code == 401
    allowed = _sale(client, manager, pump, c, qty="6.000", credit_override={"approver_id": owner_id, "credential": PASSWORD, "reason": "regular client, pays Friday"})
    assert allowed.status_code == 201, allowed.text
    d = _detail(client, manager, c)
    assert D(d["balance"]) == D("2100.00") and len(d["overrides"]) == 1
    ov = d["overrides"][0]
    assert (ov["amount"], ov["outstanding_before"], ov["credit_limit"], ov["reason"]) == ("600.00", "1500.00", "2000.00", "regular client, pays Friday")
    assert ov["approved_by"] == "owner1"
    events = audit_events(session_factory, "credit_limit_override")
    assert len(events) == 1 and "regular client, pays Friday" in events[0].description
    assert audit_events(session_factory, "credit_sale_blocked") == []
    assert audit_chain_ok(session_factory)
    # the limit itself is unchanged: the override was for one sale only
    assert client.get("/api/credit/accounts", headers=manager).json()[0]["credit_limit"] == "2000.00"
    assert _sale(client, manager, pump, c, qty="1.000").status_code == 409


def test_a_manager_cannot_approve_an_override(client, manager, pump, session_factory):
    from app.models.user import User

    c = _customer(client, manager)
    _account(client, manager, c, limit="500.00")
    s = session_factory()
    manager_id = s.query(User).filter_by(username="manager1").first().id
    s.close()
    assert all(a["id"] != manager_id for a in client.get("/api/credit/approvers", headers=manager).json())
    r = _sale(client, manager, pump, c, qty="6.000", credit_override={"approver_id": manager_id, "credential": PASSWORD, "reason": "me"})
    assert r.status_code == 403  # a correct password is not enough: the person must hold credit.override


def test_block_mode_refuses_without_any_override(client, manager, owner, pump, session_factory):
    c = _customer(client, manager)
    _account(client, manager, c, limit="500.00")
    assert client.put("/api/pump-settings/credit_over_limit", headers=owner, json={"value": "block"}).status_code == 200
    r = _sale(client, manager, pump, c, qty="6.000", credit_override={"approver_id": _owner_id(client, manager), "credential": PASSWORD, "reason": "please"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict" and "block" in r.json()["error"]["message"]
    assert audit_events(session_factory, "credit_sale_blocked")  # never silent


def test_a_sale_inside_the_limit_needs_nothing_extra(client, manager, pump):
    c = _customer(client, manager)
    _account(client, manager, c, limit="5000.00")
    assert _sale(client, manager, pump, c).status_code == 201
    assert _detail(client, manager, c)["overrides"] == []


# ---------------------------------------------------------------------------- approval of new credit customers (V-10)
def test_approval_rule_off_records_who_opened_the_account(client, manager, pump):
    c = _customer(client, manager)
    _account(client, manager, c)
    d = _detail(client, manager, c)
    assert d["approval"] == "not_required" and d["approved_by"] == "manager1" and d["approved_at"]


def test_approval_rule_on_blocks_credit_until_an_owner_approves(client, manager, owner, pump, session_factory):
    assert client.put("/api/pump-settings/new_customer_approval", headers=owner, json={"value": "on"}).status_code == 200
    c = _customer(client, manager)
    _account(client, manager, c)
    assert _detail(client, manager, c)["approval"] == "pending"
    blocked = _sale(client, manager, pump, c)
    assert blocked.status_code == 409 and "approve" in blocked.json()["error"]["message"]
    assert client.post(f"/api/credit/approvals/{c['id']}", headers=manager, json={"approve": True}).status_code == 403
    ok = client.post(f"/api/credit/approvals/{c['id']}", headers=owner, json={"approve": True, "note": "known family firm"})
    assert ok.status_code == 200
    d = _detail(client, manager, c)
    assert d["approval"] == "approved" and d["approved_by"] == "owner1" and d["approved_at"]
    assert _sale(client, manager, pump, c).status_code == 201
    assert audit_events(session_factory, "credit_customer_approved")


# ---------------------------------------------------------------------------- recovery
def test_follow_ups_promises_and_the_chase_list(client, manager, accountant, data_entry, owner, pump):
    kept, late, quiet = (_customer(client, manager, n) for n in ("Promised Today", "Gone Quiet", "Within Terms"))
    for c in (kept, late, quiet):
        _account(client, manager, c, limit="900000.00")
    _bowser_bill(client, manager, kept, "K1", 40)
    _bowser_bill(client, manager, late, "L1", 50)
    _bowser_bill(client, manager, quiet, "Q1", 2)
    f = client.post(f"/api/credit/customers/{kept['id']}/follow-ups", headers=accountant, json={
        "method": "call", "note": "says Friday", "promised_date": TODAY.isoformat(), "promised_amount": "5000.00"})
    assert f.status_code == 201 and f.json()["by"] == "accountant1" and f.json()["status"] == "open"
    assert client.post(f"/api/credit/customers/{kept['id']}/follow-ups", headers=data_entry, json={"method": "call"}).status_code == 403
    assert client.post(f"/api/credit/customers/{kept['id']}/follow-ups", headers=accountant, json={"method": "carrier pigeon"}).status_code == 422
    assert client.post(f"/api/credit/customers/{kept['id']}/follow-ups", headers=accountant, json={"method": "call", "promised_amount": "10.00"}).status_code == 422
    chase = client.get("/api/credit/chase", headers=owner).json()
    assert [(i["name"], i["reason"]) for i in chase] == [("Promised Today", "promise"), ("Gone Quiet", "overdue")]
    assert chase[0]["promised_amount"] == "5000.00" and "today" in chase[0]["detail"] and "never contacted" in chase[1]["detail"]
    # paying up removes the promise from the list; closing the follow-up is recorded
    _pay(client, manager, kept, str(D("9000.00")))
    assert [i["name"] for i in client.get("/api/credit/chase", headers=owner).json()] == ["Gone Quiet"]
    done = client.post(f"/api/credit/follow-ups/{f.json()['id']}/close", headers=accountant, json={"outcome": "kept"})
    assert done.status_code == 200 and done.json()["status"] == "kept"
    assert client.post(f"/api/credit/follow-ups/{f.json()['id']}/close", headers=accountant, json={"outcome": "broken"}).status_code == 409
    assert [x["status"] for x in _detail(client, manager, kept)["follow_ups"]] == ["kept"]


# ---------------------------------------------------------------------------- statements
def test_statement_is_bill_wise_and_date_wise_with_vehicle_and_slip(client, manager, pump):
    c = _customer(client, manager)
    _account(client, manager, c, limit="50000.00")
    _bowser_bill(client, manager, c, "B1", 20, qty="100.000", rate="90.00", transport="100.00", vehicle_no="MH14XX0001", slip_no="S-1")
    sale = _sale(client, manager, pump, c).json()
    assert client.put(f"/api/credit/bills/{sale['id']}/details", headers=manager, json={"vehicle_no": "MH12AB1234", "slip_no": "S-2"}).status_code == 200
    _pay(client, manager, c, "3000.00")
    frm, to = (TODAY - timedelta(days=30)).isoformat(), TODAY.isoformat()
    s = client.get(f"/api/credit/customers/{c['id']}/statement?date_from={frm}&date_to={to}", headers=manager).json()
    assert D(s["opening_balance"]) == 0 and D(s["closing_balance"]) == D("9100.00") + D("1000.00") - D("3000.00")
    docs = [(l["document"], l["vehicle_no"], l["slip_no"]) for l in s["lines"]]
    assert ("Bowser bill B1", "MH14XX0001", "S-1") in docs
    assert any(d[1] == "MH12AB1234" and d[2] == "S-2" for d in docs)
    assert [b["ref"] for b in s["bills"]][0] == "B1" and s["report"]["headers"][:3] == ["Date", "Document", "Vehicle"]
    # a range after everything: the opening balance carries, no lines
    later = (TODAY + timedelta(days=5)).isoformat()
    s2 = client.get(f"/api/credit/customers/{c['id']}/statement?date_from={later}&date_to={later}", headers=manager).json()
    assert s2["lines"] == [] and D(s2["opening_balance"]) == D(s["closing_balance"])
    pdf = client.get(f"/api/credit/customers/{c['id']}/statement.pdf?date_from={frm}&date_to={to}", headers=manager)
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"
    xlsx = client.get(f"/api/credit/customers/{c['id']}/statement.xlsx?date_from={frm}&date_to={to}", headers=manager)
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
    assert client.get(f"/api/credit/customers/{c['id']}/statement?date_from={to}&date_to={frm}", headers=manager).status_code == 422


# ---------------------------------------------------------------------------- checks and permissions
def test_credit_checks_appear_and_pass_for_a_normal_day(client, manager, owner, pump):
    c = _customer(client, manager)
    _account(client, manager, c, limit="5000.00")
    _sale(client, manager, pump, c)
    _pay(client, manager, c, "100.00")
    body = client.get(f"/api/checks?day={TODAY.isoformat()}", headers=owner).json()
    by_key = {}
    for r in body["results"]:
        by_key.setdefault(r["key"], []).append(r)
    for key in ("credit.shift_credit_equals_customer_bills", "credit.balance_is_bills_minus_payments", "credit.bill_within_limit_or_overridden"):
        assert key in by_key and all(r["status"] == "pass" for r in by_key[key]), key


def test_an_overridden_bill_passes_its_limit_check_and_says_so(client, manager, owner, pump):
    c = _customer(client, manager)
    _account(client, manager, c, limit="500.00")
    r = _sale(client, manager, pump, c, qty="6.000", credit_override={"approver_id": _owner_id(client, manager), "credential": PASSWORD, "reason": "ok"})
    assert r.status_code == 201
    rows = [x for x in client.get(f"/api/checks?day={TODAY.isoformat()}", headers=owner).json()["results"] if x["key"] == "credit.bill_within_limit_or_overridden"]
    assert rows and rows[0]["status"] == "pass" and "an owner allowed it" in rows[0]["sentence"]


def test_credit_control_needs_a_signed_in_person_with_credit_view(client, manager, attendant, pump):
    c = _customer(client, manager)
    _account(client, manager, c)
    for path in ("/api/credit/customers", f"/api/credit/customers/{c['id']}", "/api/credit/ageing", "/api/credit/chase",
                 f"/api/credit/check?customer_id={c['id']}&amount=1.00", "/api/credit/approvers"):
        assert client.get(path, headers=attendant).status_code == 403, path
        assert client.get(path, headers={"X-Launch-Secret": client.headers["X-Launch-Secret"]}).status_code == 401, path

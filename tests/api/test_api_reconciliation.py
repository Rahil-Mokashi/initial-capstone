from api_helpers import audit_chain_ok, audit_events
from test_api_sales import pump  # noqa: F401  (fixture)


def _cash_sale(client, h, pump, value="1000.00"):
    body = {"mode": "amount", "value": value, "payment_method": "cash", "shift_id": pump["shift"]["id"], "nozzle_id": pump["nozzle"]["id"], "employee_id": pump["employee_id"]}
    r = client.post("/api/terminal/sales", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _expected(client, h, shift_id):
    return client.get(f"/api/reconciliation/expected?shift_id={shift_id}", headers=h).json()


def test_expected_amounts_and_exact_declaration(client, manager, accountant, pump, session_factory):
    _cash_sale(client, manager, pump)
    sid = pump["shift"]["id"]
    exp = _expected(client, accountant, sid)
    cash = next(e for e in exp if e["tender"] == "Cash")
    assert cash["expected"] == "1000.00"
    r = client.post("/api/reconciliation", headers=manager, json={"shift_id": sid, "declared_amounts": {cash["tender_id"]: "1000.00"}, "remarks": "all good"})
    assert r.status_code == 201, r.text
    assert r.json()["classification"] == "normal" and r.json()["status"] == "accepted"
    assert r.json()["lines"][0]["tender"] == "Cash" and r.json()["lines"][0]["variance"] == "0.00"
    assert client.get("/api/reconciliation", headers=accountant).json()[0]["shift"].endswith("Morning")
    assert client.post("/api/reconciliation", headers=manager, json={"shift_id": sid, "declared_amounts": {cash["tender_id"]: "1000"}}).status_code == 409
    assert audit_chain_ok(session_factory)


def test_missing_declaration_and_validation(client, manager, accountant, pump):
    _cash_sale(client, manager, pump)
    sid = pump["shift"]["id"]
    assert client.post("/api/reconciliation", headers=manager, json={"shift_id": sid, "declared_amounts": {}}).status_code == 422
    cash = next(e for e in _expected(client, manager, sid) if e["tender"] == "Cash")
    assert client.post("/api/reconciliation", headers=manager, json={"shift_id": sid, "declared_amounts": {cash["tender_id"]: "-1"}}).status_code == 422
    assert client.post("/api/reconciliation", headers=manager, json={"shift_id": sid, "declared_amounts": {cash["tender_id"]: 5.5}}).status_code == 422
    assert client.post("/api/reconciliation", headers=accountant, json={"shift_id": sid, "declared_amounts": {cash["tender_id"]: "1"}}).status_code == 403


def test_big_shortage_needs_approval_then_is_booked_against_an_employee_and_recovered(
    client, manager, admin, accountant, pump, employee_id, session_factory
):
    _cash_sale(client, manager, pump, "1000.00")
    sid = pump["shift"]["id"]
    cash = next(e for e in _expected(client, manager, sid) if e["tender"] == "Cash")
    r = client.post("/api/reconciliation", headers=manager, json={"shift_id": sid, "declared_amounts": {cash["tender_id"]: "900.00"}})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert r.json()["lines"][0]["variance"] == "-100.00"
    assert r.json()["status"] == "pending_approval" and r.json()["classification"] == "approval_required"
    assert client.post(f"/api/reconciliation/{rid}/approve", headers=accountant, json={}).status_code == 403
    ok = client.post(f"/api/reconciliation/{rid}/approve", headers=manager, json={"remarks": "seen"})
    assert ok.status_code == 200 and ok.json()["status"] != "pending_approval"
    # book the shortage against the employee
    opts = client.get("/api/shortages/options", headers=manager).json()
    assert len(opts["unbooked_lines"]) == 1 and "short 100.00" in opts["unbooked_lines"][0]["label"]
    booked = client.post("/api/shortages", headers=manager, json={"shift_reconciliation_line_id": opts["unbooked_lines"][0]["id"], "employee_id": employee_id, "notes": "counted twice"})
    assert booked.status_code == 201, booked.text
    s = booked.json()
    assert s["amount"] == "100.00" and s["outstanding"] == "100.00" and s["status"] == "Outstanding" and s["employee"] == "Ravi Kumar"
    assert client.post("/api/shortages", headers=manager, json={"shift_reconciliation_line_id": opts["unbooked_lines"][0]["id"], "employee_id": employee_id}).status_code == 409
    # the repayment lands in a shift's cash book, which must exist first
    assert client.post("/api/shortages/recoveries", headers=manager, json={"employee_cash_shortage_id": s["id"], "shift_id": sid, "amount": "40.00"}).status_code in (404, 409, 422)
    assert client.post("/api/cash-book/movements", headers=manager, json={"shift_id": sid, "advance_amount": "0", "final_amount": "900"}).status_code == 201
    rec = client.post("/api/shortages/recoveries", headers=manager, json={"employee_cash_shortage_id": s["id"], "shift_id": sid, "amount": "40.00", "notes": "part"})
    assert rec.status_code == 201, rec.text
    row = client.get("/api/shortages", headers=manager).json()[0]
    assert row["recovered"] == "40.00" and row["outstanding"] == "60.00" and row["tender"] == "Cash"
    assert [o["label"] for o in client.get("/api/shortages/options", headers=manager).json()["outstanding_shortages"]][0].endswith("outstanding 60.00")
    assert audit_chain_ok(session_factory)


def test_cash_book_movements_deposits_and_summary(client, manager, accountant, attendant, pump, session_factory):
    sid = pump["shift"]["id"]
    assert client.get("/api/cash-book", headers=accountant).json() == []
    m = client.post("/api/cash-book/movements", headers=manager, json={"shift_id": sid, "advance_amount": "500.00", "final_amount": "2000.00"})
    assert m.status_code == 201, m.text
    row = client.get("/api/cash-book", headers=accountant).json()[0]
    assert row["advance_amount"] == "500.00" and row["final_amount"] == "2000.00" and row["bank_deposits_total"] == "0.00"
    d = client.post("/api/cash-book/deposits", headers=manager, json={"shift_id": sid, "bank_name": "HDFC Bank", "amount": "700.00"})
    assert d.status_code == 201, d.text
    row = client.get("/api/cash-book", headers=accountant).json()[0]
    assert row["bank_deposits_total"] == "700.00" and row["opening_balance"] == "0.00" and row["closing_cash_in_hand"] == "1800.00"
    assert client.post("/api/cash-book/deposits", headers=manager, json={"shift_id": sid, "bank_name": " ", "amount": "1"}).status_code == 422
    assert client.post("/api/cash-book/deposits", headers=manager, json={"shift_id": sid, "bank_name": "X", "amount": "0"}).status_code == 422
    assert client.post("/api/cash-book/movements", headers=manager, json={"shift_id": sid, "advance_amount": "-1"}).status_code == 422
    assert client.post("/api/cash-book/movements", headers=attendant, json={"shift_id": sid}).status_code == 403
    assert client.get("/api/cash-book", headers=attendant).status_code == 403
    assert audit_chain_ok(session_factory)

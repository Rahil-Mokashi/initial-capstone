from api_helpers import audit_chain_ok, audit_events


def _category(client, h, name="Tea & snacks"):
    r = client.post("/api/expense-categories", headers=h, json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def _expense(client, h, cat, employee_id, **over):
    body = {"category_id": cat["id"], "amount": "250.00", "payment_method": "cash", "employee_id": employee_id, **over}
    return client.post("/api/expenses", headers=h, json=body)


def test_categories_and_permissions(client, manager, accountant, attendant, session_factory):
    c = _category(client, manager)
    assert c["status"] == "active"
    assert client.post("/api/expense-categories", headers=manager, json={"name": " "}).status_code == 422
    assert client.post("/api/expense-categories", headers=manager, json={"name": "Tea & snacks"}).status_code in (409, 422)
    assert client.post("/api/expense-categories", headers=attendant, json={"name": "X"}).status_code == 403
    assert "Tea & snacks" in [x["name"] for x in client.get("/api/expense-categories", headers=accountant).json()]
    assert client.get("/api/expense-categories", headers=attendant).status_code == 403
    assert audit_chain_ok(session_factory)


def test_record_list_options_and_validation(client, manager, accountant, attendant, employee_id, session_factory):
    c = _category(client, manager)
    r = _expense(client, manager, c, employee_id, receipt_reference="B-1", description="tea")
    assert r.status_code == 201, r.text
    e = r.json()
    assert e["amount"] == "250.00" and e["category"] == "Tea & snacks" and e["employee"] == "Ravi Kumar" and e["status"] in ("pending", "approved")
    opts = client.get("/api/expenses/options", headers=accountant).json()
    assert "Tea & snacks" in [x["label"] for x in opts["categories"]] and opts["employees"] and opts["shifts"] == []
    assert len(client.get("/api/expenses", headers=accountant).json()) == 1
    assert _expense(client, manager, c, employee_id, amount="0").status_code == 422
    assert _expense(client, manager, c, employee_id, amount="1.005").status_code == 422
    assert _expense(client, manager, c, employee_id, payment_method="credit").status_code == 422
    assert _expense(client, manager, c, "nope").status_code == 404
    assert _expense(client, attendant, c, employee_id).status_code == 403
    assert len(audit_events(session_factory, "expense_recorded")) == 1 and audit_chain_ok(session_factory)


def test_approve_and_reject(client, manager, attendant, employee_id, session_factory):
    c = _category(client, manager)
    a = _expense(client, manager, c, employee_id).json()
    b = _expense(client, manager, c, employee_id, amount="99.00").json()
    assert a["status"] == "pending"
    ok = client.post(f"/api/expenses/{a['id']}/approve", headers=manager, json={})
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    rej = client.post(f"/api/expenses/{b['id']}/reject", headers=manager, json={})
    assert rej.status_code == 200 and rej.json()["status"] == "rejected"
    assert client.post(f"/api/expenses/{a['id']}/reject", headers=manager, json={}).status_code in (409, 422)
    assert client.post(f"/api/expenses/{b['id']}/approve", headers=attendant, json={}).status_code == 403
    assert client.post("/api/expenses/nope/approve", headers=manager, json={}).status_code == 404
    assert audit_chain_ok(session_factory)

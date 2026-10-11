from api_helpers import audit_chain_ok, audit_events
from test_api_sales import pump  # noqa: F401  (fixture)


def _customer(client, h, name="ACME"):
    return client.post("/api/customers", headers=h, json={"name": name}).json()


def _account(client, h, customer, limit="10000.00", days=30):
    return client.post("/api/credit/accounts", headers=h, json={"customer_id": customer["id"], "credit_limit": limit, "payment_due_days": days})


def test_open_list_and_validation(client, manager, accountant, attendant, session_factory):
    c = _customer(client, manager)
    a = _account(client, manager, c)
    assert a.status_code == 201, a.text
    assert a.json()["customer"] == "ACME" and a.json()["credit_limit"] == "10000.00" and a.json()["outstanding"] == "0.00" and a.json()["overdue"] is False
    assert _account(client, manager, c).status_code in (409, 422)  # one account per customer
    assert _account(client, manager, _customer(client, manager, "B"), limit="0").status_code == 422
    assert _account(client, manager, _customer(client, manager, "C"), limit="10.005").status_code == 422
    assert _account(client, manager, _customer(client, manager, "D"), days=0).status_code == 422
    assert _account(client, accountant, c).status_code == 403
    assert len(client.get("/api/credit/accounts", headers=accountant).json()) == 1
    assert client.get("/api/credit/accounts", headers=attendant).status_code == 403
    assert audit_chain_ok(session_factory)


def test_credit_sale_payment_statement_and_limit(client, manager, accountant, pump, session_factory):
    c = _customer(client, manager)
    _account(client, manager, c, limit="2000.00")
    body = {"mode": "amount", "value": "1500.00", "payment_method": "credit", "customer_id": c["id"], "shift_id": pump["shift"]["id"], "nozzle_id": pump["nozzle"]["id"], "employee_id": pump["employee_id"]}
    assert client.post("/api/terminal/sales", headers=manager, json=body).status_code == 201
    acc = client.get("/api/credit/accounts", headers=accountant).json()[0]
    assert acc["outstanding"] == "1500.00"
    # a second sale would pass the limit
    over = client.post("/api/terminal/sales", headers=manager, json={**body, "value": "600.00"})
    assert over.status_code in (409, 422)
    pay = client.post("/api/credit/payments", headers=manager, json={"customer_id": c["id"], "amount": "500.00", "payment_method": "cash", "reference": "r1"})
    assert pay.status_code == 201 and pay.json()["amount"] == "500.00"
    assert client.get("/api/credit/accounts", headers=accountant).json()[0]["outstanding"] == "1000.00"
    assert client.post("/api/credit/payments", headers=accountant, json={"customer_id": c["id"], "amount": "1", "payment_method": "cash"}).status_code == 403
    st = client.get(f"/api/credit/accounts/{c['id']}/statement", headers=accountant).json()
    assert st["customer"] == "ACME" and st["running_balance"] == "1000.00"
    assert [e["debit"] for e in st["entries"]] == ["1500.00", None] and st["entries"][1]["credit"] == "500.00"
    assert st["report"]["title"] == "Customer Statement - ACME" and st["report"]["rows"][-1][1] == "Running Balance" and "<table" in st["report"]["html"]
    lim = client.post(f"/api/credit/accounts/{c['id']}/limit", headers=manager, json={"new_limit": "5000.00"})
    assert lim.status_code == 200 and lim.json()["credit_limit"] == "5000.00"
    assert len(audit_events(session_factory, "credit_limit_changed")) == 1 and audit_chain_ok(session_factory)


def test_statement_downloads(client, manager, accountant):
    c = _customer(client, manager)
    _account(client, manager, c)
    pdf = client.get(f"/api/credit/accounts/{c['id']}/statement.pdf", headers=accountant)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and "customer_statement" in pdf.headers["content-disposition"]
    xlsx = client.get(f"/api/credit/accounts/{c['id']}/statement.xlsx", headers=accountant)
    assert xlsx.status_code == 200 and xlsx.content.startswith(b"PK")
    assert client.get(f"/api/credit/accounts/{c['id']}/statement.exe", headers=accountant).status_code == 422

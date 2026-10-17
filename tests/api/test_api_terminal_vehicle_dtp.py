"""Terminal: the vehicle number (required, stored one way, shown where the owners look), DTP Card as the shift's own sum,
and a credit sale counted exactly once whichever screen it was typed on."""

from datetime import date, timedelta
from decimal import Decimal

from test_api_close_desk import _modes, _setup
from test_api_credit_control import _account, _customer
from test_api_sales import pump  # noqa: F401  (fixture)

D = Decimal
TODAY = date.today()


def _terminal(client, h, pump, **over):
    body = {"mode": "amount", "value": "1000.00", "payment_method": "credit", "vehicle_number": "mh 12 ab 1234",
            "shift_id": pump["shift"]["id"], "nozzle_id": pump["nozzle"]["id"], "employee_id": pump["employee_id"]}
    return client.post("/api/terminal/sales", headers=h, json={**body, **over})


def test_the_vehicle_number_is_required_and_saved_upper_case_without_spaces(client, manager, pump):
    c = _customer(client, manager)
    _account(client, manager, c)
    body = {"mode": "amount", "value": "1000.00", "payment_method": "credit", "customer_id": c["id"],
            "shift_id": pump["shift"]["id"], "nozzle_id": pump["nozzle"]["id"], "employee_id": pump["employee_id"]}
    assert client.post("/api/terminal/sales", headers=manager, json=body).status_code == 422
    r = _terminal(client, manager, pump, customer_id=c["id"])
    assert r.status_code == 201, r.text
    assert r.json()["vehicle_number"] == "MH12AB1234"
    # on the receipt, the customer statement, the daily report
    receipt = client.get(f"/api/sales/{r.json()['id']}/receipt", headers=manager).json()["html"]
    assert "MH12AB1234" in receipt
    frm, to = (TODAY - timedelta(days=1)).isoformat(), TODAY.isoformat()
    st = client.get(f"/api/credit/customers/{c['id']}/statement?date_from={frm}&date_to={to}", headers=manager).json()
    assert [l["vehicle_no"] for l in st["lines"] if l["vehicle_no"]] == ["MH12AB1234"]
    bills = client.get(f"/api/credit/customers/{c['id']}", headers=manager).json()
    assert "MH12AB1234" in str(bills)
    rep = client.get(f"/api/daily-report?day={TODAY.isoformat()}&style=classic", headers=manager).json()
    assert "MH12AB1234" in rep["html"]


def test_dtp_card_is_the_sum_of_the_shifts_terminal_sales_and_is_not_typed(client, data_entry, manager, employee_id):
    nozzle, shift, _ = _setup(client, manager)
    emp = employee_id
    pump_like = {"shift": shift, "nozzle": nozzle, "employee_id": emp}
    for v in ("1000.00", "250.50"):
        r = _terminal(client, manager, pump_like, payment_method="dtp_card", value=v)
        assert r.status_code == 201, r.text
    desk = client.get(f"/api/close-shift/{shift['id']}", headers=data_entry).json()
    dtp = next(m for m in desk["modes"] if m["label"] == "DTP Card")
    assert dtp["read_only"] is True and dtp["count"] == 2 and dtp["amount"] == "1250.50"
    # typing a second DTP figure is refused, and the report uses the same sum
    modes = _modes(client, data_entry, shift["id"])
    typed = client.post(f"/api/close-shift/{shift['id']}", headers=data_entry, json={"modes": [{"tender_id": modes["DTP Card"], "amount": "999.00"}]})
    assert typed.status_code == 409
    rep = client.get(f"/api/daily-report?day={TODAY.isoformat()}&style=classic", headers=manager).json()["report"]
    block = rep["shifts"][0]
    lines = {l[0] if isinstance(l, list) else l["label"]: (l[1] if isinstance(l, list) else l["amount"]) for l in block["lines"]}
    assert D(str(lines["DTP Card"])) == D("1250.50")


def test_a_credit_sale_is_counted_once_whichever_screen_typed_it(client, manager, accountant, pump):
    c = _customer(client, manager)
    _account(client, manager, c, limit="50000.00")
    via_terminal = _terminal(client, manager, pump, customer_id=c["id"], value="1000.00")
    via_bill = client.post("/api/sales", headers=manager, json={
        "shift_id": pump["shift"]["id"], "nozzle_id": pump["nozzle"]["id"], "employee_id": pump["employee_id"],
        "quantity": "5.000", "payment_method": "credit", "customer_id": c["id"], "vehicle_number": "MH14XX0001"})
    assert via_terminal.status_code == 201 and via_bill.status_code == 201
    total = D("1000.00") + D("500.00")
    # the customer's balance, once
    acc = next(a for a in client.get("/api/credit/accounts", headers=accountant).json() if a["customer_id"] == c["id"])
    assert D(acc["outstanding"]) == total
    # ageing, once
    ageing = client.get("/api/credit/ageing", headers=manager).json()
    row = next(r for r in ageing["rows"] if r["customer_id"] == c["id"])
    assert D(row["balance"]) == total
    # the statement: two lines, closing balance once
    frm, to = (TODAY - timedelta(days=1)).isoformat(), TODAY.isoformat()
    st = client.get(f"/api/credit/customers/{c['id']}/statement?date_from={frm}&date_to={to}", headers=manager).json()
    assert len(st["lines"]) == 2 and D(st["closing_balance"]) == total
    # the daily report: CreditSale is one line, equal to the two bills, listed as two bills
    rep = client.get(f"/api/daily-report?day={TODAY.isoformat()}&style=classic", headers=manager).json()["report"]
    block = rep["shifts"][0]
    lines = {l[0] if isinstance(l, list) else l["label"]: (l[1] if isinstance(l, list) else l["amount"]) for l in block["lines"]}
    assert D(str(lines["CreditSale"])) == total
    assert len(block["credit_sales"]) == 2

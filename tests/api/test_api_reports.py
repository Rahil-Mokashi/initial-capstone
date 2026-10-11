from api_helpers import audit_chain_ok  # noqa: F401
from test_api_sales import pump  # noqa: F401  (fixture)

ALL_KEYS = [
    "fuel_type_summary", "sales_report", "payment_summary_report", "expense_summary_report", "credit_fuel_type_report",
    "customer_outstanding_report", "reconciliation_report", "daily_summary_report", "attendant_nozzle_report",
    "fuel_movement_report", "cash_book", "attendance_report",
]


def _sale(client, h, pump, value="1000.00"):
    body = {"mode": "amount", "value": value, "payment_method": "cash", "shift_id": pump["shift"]["id"], "nozzle_id": pump["nozzle"]["id"], "employee_id": pump["employee_id"]}
    assert client.post("/api/terminal/sales", headers=h, json=body).status_code == 201


def test_hub_lists_reports_by_permission(client, manager, accountant, attendant):
    full = client.get("/api/reports", headers=manager).json()
    assert [r["key"] for r in full["reports"]] == ALL_KEYS and full["insights"] is True
    sales = next(r for r in full["reports"] if r["key"] == "sales_report")
    assert sales["dates"] is True and sales["filters"] == []
    att = next(r for r in full["reports"] if r["key"] == "attendant_nozzle_report")
    assert att["filters"] == ["employee", "nozzle"]
    assert next(r for r in full["reports"] if r["key"] == "credit_fuel_type_report")["dates"] is False
    # an attendant holds sale.view only: the sales-based reports, nothing else
    mine = [r["key"] for r in client.get("/api/reports", headers=attendant).json()["reports"]]
    assert "sales_report" in mine and "cash_book" not in mine and "customer_outstanding_report" not in mine


def test_every_report_runs_and_returns_printable_html(client, manager, pump):
    _sale(client, manager, pump)
    for key in ALL_KEYS:
        r = client.get(f"/api/reports/{key}", headers=manager)
        assert r.status_code == 200, (key, r.text)
        body = r.json()
        assert body["title"] and body["headers"] is not None and "<table" in body["html"], key


def test_sales_report_figures_and_date_window(client, manager, accountant, pump):
    _sale(client, manager, pump, "1000.00")
    body = client.get("/api/reports/sales_report", headers=accountant).json()
    assert body["title"] == "Sales Report" and body["headers"] == ["Fuel Type", "Sales", "Quantity (L)", "Amount"]
    assert body["rows"][-1] == ["Total", "1", "10.00", "1000.00"]
    assert body["volume_columns"] == [2] and body["money_columns"] == [3]
    empty = client.get("/api/reports/sales_report?date_from=2000-01-01&date_to=2000-01-02", headers=accountant).json()
    assert empty["rows"][-1][:2] == ["Total", "0"]
    assert client.get("/api/reports/sales_report?date_from=nope", headers=accountant).status_code == 422


def test_filters_pass_only_when_set(client, manager, pump, employee_id):
    _sale(client, manager, pump)
    opts = client.get("/api/reports/filter-options", headers=manager).json()
    assert opts["employees"][0]["value"] == employee_id and opts["nozzles"][0]["label"] == "N1"
    all_rows = client.get("/api/reports/attendant_nozzle_report", headers=manager).json()["rows"]
    mine = client.get(f"/api/reports/attendant_nozzle_report?employee_id={employee_id}&nozzle_id={pump['nozzle']['id']}", headers=manager).json()["rows"]
    other = client.get("/api/reports/attendant_nozzle_report?employee_id=someone-else", headers=manager).json()["rows"]
    assert len(mine) >= 1 and len(other) < len(all_rows) or other != all_rows
    # a filter the report does not support is ignored, not an error
    assert client.get("/api/reports/sales_report?employee_id=x", headers=manager).status_code == 200


def test_filter_options_hide_the_staff_roster_from_people_who_may_not_see_it(client, attendant):
    o = client.get("/api/reports/filter-options", headers=attendant).json()
    assert o["employees"] == []  # attendants hold sale.view but not employee.view


def test_permissions_and_unknown_report(client, attendant, accountant):
    assert client.get("/api/reports/cash_book", headers=attendant).status_code == 403
    assert client.get("/api/reports/customer_outstanding_report", headers=attendant).status_code == 403
    assert client.get("/api/reports/nope", headers=accountant).status_code == 404


def test_exports_are_real_files_with_matching_data(client, manager, accountant, pump):
    _sale(client, manager, pump)
    pdf = client.get("/api/reports/sales_report/export.pdf", headers=accountant)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and "sales_report.pdf" in pdf.headers["content-disposition"]
    xlsx = client.get("/api/reports/sales_report/export.xlsx", headers=accountant)
    assert xlsx.status_code == 200 and xlsx.content.startswith(b"PK")
    csv = client.get("/api/reports/sales_report/export.csv", headers=accountant)
    assert csv.status_code == 200 and b"Fuel Type" in csv.content and b"1000.00" in csv.content
    # the export honours the same filters as the screen
    empty = client.get("/api/reports/sales_report/export.csv?date_from=2000-01-01&date_to=2000-01-02", headers=accountant)
    assert b"1000.00" not in empty.content
    assert client.get("/api/reports/sales_report/export.exe", headers=accountant).status_code == 422
    assert client.get("/api/reports/cash_book/export.pdf", headers=accountant).status_code in (200, 403)


def test_fuel_type_summary_cards(client, manager, accountant, tank):
    cards = client.get("/api/reports/fuel-type-summary/cards", headers=accountant).json()
    petrol = next(c for c in cards if c["tank_count"] == 1)
    assert petrol["total_capacity"] == "10000.000" and petrol["total_current_stock"] == "2500.500"
    table = client.get("/api/reports/fuel_type_summary", headers=accountant).json()
    assert table["headers"][0] == "Fuel Type" and table["volume_columns"] == [2, 3]

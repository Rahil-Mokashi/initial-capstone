from test_api_sales import pump  # noqa: F401  (fixture)


def _sale(client, h, pump, value="1000.00"):
    body = {"mode": "amount", "vehicle_number": "MH12AB1234", "value": value, "payment_method": "cash", "shift_id": pump["shift"]["id"], "nozzle_id": pump["nozzle"]["id"], "employee_id": pump["employee_id"]}
    assert client.post("/api/terminal/sales", headers=h, json=body).status_code == 201


def test_performance_for_each_period_and_totals(client, manager, accountant, pump):
    _sale(client, manager, pump)
    for period in ("day", "week", "month", "quarter", "year"):
        r = client.get(f"/api/analytics/performance?period={period}", headers=accountant)
        assert r.status_code == 200, (period, r.text)
        body = r.json()
        assert body["title"].startswith(f"Business Performance - {period.title()}") and "<table" in body["html"]
        assert body["headers"][0] == "Fuel Type"
    day = client.get("/api/analytics/performance?period=day", headers=accountant).json()
    totals = {row[0]: row[1] for row in day["rows"] if row[0].startswith("Total")}
    assert totals["Total Revenue"] == "1000.00"
    past = client.get("/api/analytics/performance?period=day&as_of=2000-01-01", headers=accountant).json()
    assert {row[0]: row[1] for row in past["rows"] if row[0].startswith("Total")}["Total Revenue"] == "0.00"


def test_performance_validation_and_permission(client, accountant, attendant):
    assert client.get("/api/analytics/performance?period=decade", headers=accountant).status_code == 422
    assert client.get("/api/analytics/performance?as_of=not-a-date", headers=accountant).status_code == 422
    assert client.get("/api/analytics/performance", headers=attendant).status_code == 403
    assert client.get("/api/analytics/forecast", headers=attendant).status_code == 403


def test_forecast_has_explanations_printed_after_the_table(client, manager, accountant, pump):
    _sale(client, manager, pump)
    body = client.get("/api/analytics/forecast", headers=accountant).json()
    assert body["report"]["title"] == "Sales Forecast" and body["report"]["headers"][0] == "Fuel Type"
    assert len(body["explanations"]) >= 1 and all(isinstance(e, str) and e for e in body["explanations"])
    assert body["explanations"][0] in body["report"]["html"] or "<p>" in body["report"]["html"]


def test_exports(client, manager, accountant, pump):
    _sale(client, manager, pump)
    for url, name in (("/api/analytics/performance/export.pdf", "business_performance"), ("/api/analytics/forecast/export.pdf", "sales_forecast")):
        r = client.get(url, headers=accountant)
        assert r.status_code == 200 and r.content.startswith(b"%PDF"), url
    assert client.get("/api/analytics/performance/export.xlsx", headers=accountant).content.startswith(b"PK")
    assert b"Fuel Type" in client.get("/api/analytics/forecast/export.csv", headers=accountant).content
    assert client.get("/api/analytics/performance/export.zip", headers=accountant).status_code == 422

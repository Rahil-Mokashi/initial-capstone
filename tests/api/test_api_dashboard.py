from datetime import date

from test_api_sales import pump  # noqa: F401  (fixture)


def _sale(client, h, pump, value="1000.00"):
    body = {"mode": "amount", "vehicle_number": "MH12AB1234", "value": value, "payment_method": "cash", "shift_id": pump["shift"]["id"], "nozzle_id": pump["nozzle"]["id"], "employee_id": pump["employee_id"]}
    assert client.post("/api/terminal/sales", headers=h, json=body).status_code == 201


def test_summary_tiles_and_permission_gating(client, manager, attendant, pump):
    _sale(client, manager, pump)
    s = client.get("/api/dashboard/summary", headers=manager).json()
    assert s["sales_today_count"] == 1 and s["sales_today_amount"] == "1000.00"
    assert s["open_shifts_count"] == 1 and s["open_shift_labels"] == ["Morning"]
    assert s["low_stock_tanks_count"] == 0 and s["pending_purchase_orders_count"] == 0
    a = client.get("/api/dashboard/summary", headers=attendant).json()
    assert a["sales_today_count"] == 1  # attendants hold sale.view
    assert a["open_shifts_count"] is None and a["low_stock_tanks_count"] is None and a["pending_purchase_orders_count"] is None


def test_sales_trend_is_oldest_first_and_exact(client, manager, pump):
    _sale(client, manager, pump)
    series = client.get("/api/dashboard/sales-trend?days=7", headers=manager).json()
    assert len(series) == 7 and series[-1]["day"] == date.today().isoformat() and series[-1]["amount"] == "1000.00"
    assert [p["day"] for p in series] == sorted(p["day"] for p in series) and all(p["amount"] == "0.00" for p in series[:-1])
    assert len(client.get("/api/dashboard/sales-trend?days=30", headers=manager).json()) == 30
    assert client.get("/api/dashboard/sales-trend?days=0", headers=manager).status_code == 422
    assert client.get("/api/dashboard/sales-trend", headers=manager).status_code == 200


def test_roster_lists_who_is_on_a_nozzle(client, manager, accountant, attendant, pump):
    rows = client.get("/api/dashboard/roster", headers=manager).json()
    assert rows == [{"name": "Ravi Kumar", "detail": rows[0]["detail"]}] and rows[0]["detail"].startswith("N1 · Petrol · Morning · since ")
    assert client.get("/api/dashboard/roster", headers=attendant).status_code == 403  # shift.view is needed


def test_alerts_computed_from_live_data(client, manager, attendant, fuel_id, tank):
    # a tank at 5% is low on fuel
    t2 = client.post("/api/tanks", headers=manager, json={"code": "T2", "fuel_id": fuel_id, "capacity": "10000", "opening_stock": "300"}).json()
    body = client.get("/api/alerts", headers=manager).json()
    assert body["total"] == len(body["notifications"]) >= 1
    low_alerts = [n for n in body["notifications"] if n["category"] == "low_fuel"]
    assert low_alerts and "T2" in (low_alerts[0]["title"] + low_alerts[0]["detail"])
    assert low_alerts[0]["severity"] in ("critical", "warning") and low_alerts[0]["action"]
    assert body["critical_count"] + body["warning_count"] <= body["total"]
    # an attendant is never told about a tank they cannot open
    mine = client.get("/api/alerts", headers=attendant).json()
    assert not [n for n in mine["notifications"] if n["category"] == "low_fuel"]
    assert t2["id"]

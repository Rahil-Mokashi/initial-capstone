"""The Classic daily report, built from a synthetic day with the same structure as the owner's report.

Every expected figure below is worked out by hand in tests/api/pump_day.py; nothing is copied from real data.
"""

from decimal import Decimal

import pytest

from api_helpers import audit_chain_ok
from pump_day import EXPECTED, TODAY, build_day

D = Decimal


@pytest.fixture()
def day(client, manager, db):
    return build_day(client, manager, db)


def _report(client, h, style="classic"):
    r = client.get(f"/api/daily-report?day={TODAY}&style={style}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _by_code(rep):
    return {c["code"]: c["tank_id"] for c in rep["report"]["tanks"]}


def test_permissions(client, day, manager, accountant, data_entry, attendant, owner):
    for h in (manager, accountant, data_entry, owner):
        assert client.get(f"/api/daily-report?day={TODAY}", headers=h).status_code == 200
    assert client.get(f"/api/daily-report?day={TODAY}", headers=attendant).status_code == 403
    assert client.get("/api/daily-report", headers={"X-Launch-Secret": client.headers["X-Launch-Secret"]}).status_code == 401


def test_sale_details_grid_formulas(client, day, manager):
    rep = _report(client, manager)["report"]
    ids = _by_code(_report(client, manager))
    assert list(ids) == ["MS-22", "MS-16", "HSD-16", "HSD-22"]  # columns are the tank names, in set-up order
    ms, hsd = ids["MS-22"], ids["HSD-16"]
    s1, s2 = rep["shifts"][0], rep["shifts"][1]

    assert D(rep["opening"][ms]) == D("35485")
    assert D(rep["purchase"][ms]) == D("23000")
    assert (D(s1["litres_by_tank"][ms]), D(s2["litres_by_tank"][ms])) == (D("995"), D("500"))
    assert D(rep["testing"][ms]) == D("5")
    # Total Stock = O/S + Purchase - Shift1 - Shift2; testing is shown but NOT added back (T-01 default)
    assert D(rep["total_stock"][ms]) == D("35485") + D("23000") - D("995") - D("500") == D("56990")
    # (+/-) = Closing Stock (dip) - Total Stock
    assert D(rep["closing"][ms]) == D("56950") and D(rep["plus_minus"][ms]) == D("-40")

    assert D(rep["total_stock"][hsd]) == D("8000") - D("500") - D("400") + D("0") + D("0") == D("7100")
    assert D(rep["plus_minus"][hsd]) == 0
    assert rep["closing"][ids["MS-16"]] is None and rep["plus_minus"][ids["MS-16"]] is None  # no dip taken: shown blank
    assert D(rep["total_stock"][ids["MS-16"]]) == D("12000")


def test_adding_testing_back_is_a_setting_default_off(client, day, manager, owner):
    ms = _by_code(_report(client, manager))["MS-22"]
    assert client.put("/api/pump-settings/add_testing_back", headers=owner, json={"value": "on"}).status_code == 200
    rep = _report(client, manager)["report"]
    assert D(rep["total_stock"][ms]) == D("56995")  # 56,990 + 5 testing
    assert rep["add_testing_back"] is True


def test_rupees_per_shift_and_fuel_only_total(client, day, manager):
    rep = _report(client, manager)["report"]
    s1, s2 = rep["shifts"]
    assert [D(s1["fuel_rs"]), D(s2["fuel_rs"])] == EXPECTED["fuel_rs"]
    assert [D(s1["oil_rs"]), D(s2["oil_rs"])] == EXPECTED["oil_rs"]
    assert [D(s1["total_sale"]), D(s2["total_sale"])] == EXPECTED["total_sale"]
    # Total Rs = sum of shift Total Sale - sum of Oil
    assert D(rep["total_rs"]) == D(s1["total_sale"]) + D(s2["total_sale"]) - D(s1["oil_rs"]) - D(s2["oil_rs"]) == EXPECTED["total_rs"]


def test_transaction_details_lines_and_total_equals_total_sale(client, day, manager):
    s1, s2 = _report(client, manager)["report"]["shifts"]
    assert [(label, D(a)) for label, a in s1["lines"]] == [
        ("CreditSale", D("20000.00")), ("CARD", D("0")), ("DTP Card", D("10000.00")), ("Other", D("0")),
        ("PHONE PAY", D("5000.00")), ("PTM", D("30000.00")), ("Expenses", D("1050.00")),
        ("Advance", D("40000.00")), ("Final", D("38950.00")),
    ]
    # Total = sum of the lines = the shift's Total Sale: the same rounded figures feed both, so they always agree
    assert D(s1["lines_total"]) == sum(D(a) for _, a in s1["lines"]) == D(s1["total_sale"]) == D("145000.00")
    assert D(s2["lines_total"]) == D(s2["total_sale"]) == D("87750.00")
    assert [l for l, _ in s2["lines"]] == [l for l, _ in s1["lines"]]


def test_cash_book_balances_and_carries_forward(client, day, manager):
    s1, s2 = _report(client, manager)["report"]["shifts"]
    assert D(s1["opening_balance"]) == 0 and D(s1["advance"]) == D("40000") and D(s1["final"]) == D("38950")
    assert [(b, D(a)) for b, a in s1["deposits"]] == [("Bank of India", D("50000.00")), ("Second Bank", D("20000.00"))]
    assert D(s1["cash_in_hand"]) == D("8950.00")
    assert D(s1["receipts_total"]) == D(s1["payments_total"]) == D("78950.00")
    # next shift's Opening Balance = previous shift's Cash in hand
    assert D(s2["opening_balance"]) == D(s1["cash_in_hand"])
    assert D(s2["cash_in_hand"]) == D("6700.00") and D(s2["receipts_total"]) == D(s2["payments_total"]) == D("66700.00")


def test_credit_sales_per_shift_include_the_stock_transfer(client, day, manager):
    s1, s2 = _report(client, manager)["report"]["shifts"]
    names1 = sorted((name, D(a)) for _, name, a in s1["credit_sales"])
    assert names1 == [("ACME Traders", D("2000.00")), ("Stock Transfer (Bouser)", D("18000.00"))]
    assert D(s1["credit_total"]) == sum(a for _, a in names1) == EXPECTED["credit_sale"][0]
    assert [(n, D(a)) for _, n, a in s2["credit_sales"]] == [("ACME Traders", D("9000.00"))]
    assert all(no for no, _, _ in s1["credit_sales"])  # every bill has a bill number


def test_expense_lines_include_internal_fuel_with_vehicle_and_litres(client, day, manager):
    s1, s2 = _report(client, manager)["report"]["shifts"]
    assert [(t, D(a)) for t, a in s1["expenses"]] == [("Tea", D("150.00")), ("Diesel Exp (MH12AB1234) 10 Lit", D("900.00"))]
    assert D(s1["expenses_total"]) == EXPECTED["expenses"][0] and s2["expenses"] == []
    assert s1["pending_expenses"] == 2  # entered, not yet approved: printed, and a check says so


def test_internal_fuel_does_not_touch_tank_stock(client, day, manager):
    tank = client.get(f"/api/tanks/{day['tanks']['HSD-16']['id']}", headers=manager).json()
    # opening 8,000 - 500 - 400 sold; the 10 L of internal fuel is NOT deducted a second time
    assert D(tank["current_stock"]) == D("7100.000")


def test_oil_sale_table(client, day, manager):
    rows = {(o["name"], o["shift_label"]): o for o in _report(client, manager)["report"]["oil_rows"]}
    a = rows[("HP Racer 1L", "Shift 1")]
    assert (D(a["opening"]), D(a["purchase"]), D(a["sale"]), D(a["balance"]), D(a["rate"]), D(a["total"])) == (
        D("10"), D("20"), D("2"), D("28"), D("250.00"), D("500.00"))  # Balance = Opening + Purchase - Sale ; Total = Sale x Rate
    b = rows[("HP Racer 1L", "Shift 2")]
    assert D(b["balance"]) == D("27") and D(b["total"]) == D("250.00")
    m = rows[("Milcy Turbo 5L", "Shift 2")]
    assert (D(m["opening"]), D(m["balance"]), D(m["total"]), m["customer"]) == (D("5"), D("4"), D("1500.00"), "Workshop")


def test_bowser_sections(client, day, manager):
    b = _report(client, manager)["report"]["bowser"]
    assert [(l["label"], D(l["litres"]), D(l["rupees"])) for l in b["stock_lines"]] == [
        ("Opening Stock", D("1000"), D("90000.00")), ("Stock Transfer", D("200"), D("18000.00"))]
    assert D(b["stock_litres"]) == D("1200") and D(b["stock_rupees"]) == D("108000.00")
    assert [(x["bill_no"], D(x["quantity"]), D(x["amount"]), D(x["transport"]), D(x["total"])) for x in b["bills"]] == [
        ("B1", D("150"), D("14250.00"), D("500.00"), D("14750.00")), ("B2", D("250"), D("23750.00"), D("1000.00"), D("24750.00"))]
    assert (D(b["bills_qty"]), D(b["bills_amount"]), D(b["bills_transport"]), D(b["bills_total"])) == (D("400"), D("38000.00"), D("1500.00"), D("39500.00"))
    assert D(b["closing_litres"]) == D("1200") - D("400") == D("800")  # Closing = A total litres - sum of B Qty
    assert D(b["closing_rupees"]) == D("72000.00")
    assert D(b["meter_net"]) == D("1400") - D("1000") - D("0") == D(b["bills_qty"])  # Net Sale = End - Start - Testing = bills


def test_html_has_two_sides_in_the_old_order_with_indian_grouping(client, day, manager):
    html = _report(client, manager)["html"]
    assert html.count('class="page"') == 2
    order = ["Sale Details", "Shift 1 Transaction Details", "Shift 2 Transaction Details", "Shift 1 Cash Book",
             "Shift 1 Credit Sale", "Expenses Details", "Oil Sale", "Bowser Van", "A] Internal stock", "B] Bill No", "C] Bowser meter"]
    positions = [html.index(s) for s in order]
    assert positions == sorted(positions)
    for label in ("MS-22", "MS-16", "HSD-16", "HSD-22", "O/S", "Purchase", "Shift1", "Shift2", "Testing", "Total Stock", "(+/-)",
                  "Closing Stock", "Total Rs", "CreditSale", "CARD", "DTP Card", "PHONE PAY", "PTM", "Advance", "Final",
                  "Opening Balance", "Cash in hand", "Stock Transfer (Bouser)", "Net Sale"):
        assert label in html, label
    assert "2,30,500.00" in html  # Total Rs, grouped 2,30,500.00 not 230,500.00
    assert "http://" not in html and "https://" not in html  # fully offline


def test_building_the_report_changes_nothing(client, day, manager, session_factory):
    from app.models.audit_log import AuditLog

    s = session_factory()
    before = s.query(AuditLog).count()
    s.close()
    _report(client, manager)
    s = session_factory()
    assert s.query(AuditLog).count() == before
    s.close()
    assert audit_chain_ok(session_factory)


# ------------------------------------------------------------------ the checks behind the report
def _checks(client, h):
    body = client.get(f"/api/checks?day={TODAY}", headers=h).json()
    return body, {}


def _keyed(client, h):
    body = client.get(f"/api/checks?day={TODAY}", headers=h).json()
    out = {}
    for r in body["results"]:
        out.setdefault(r["key"], []).append(r)
    return body, out


def test_a_good_day_has_a_check_for_every_formula_and_none_failing(client, day, manager, owner):
    client.post("/api/checks/run", headers=owner, json={"day": TODAY})
    body, by_key = _keyed(client, owner)
    for key in ("report.tank_stock_matches_book", "report.dip_matches_total_stock", "report.shift_total_equals_total_sale",
                "report.shift_credit_matches_credit_mode", "report.shift_cash_book_balances", "report.shift_cash_in_hand_not_negative",
                "report.shift_oil_equals_oil_sale", "report.next_opening_is_previous_cash_in_hand", "report.day_fuel_only_total",
                "report.bowser_meter_equals_bills", "report.bowser_closing_not_negative", "report.bowser_bill_totals",
                "report.oil_stock_not_negative", "report.every_litre_has_a_tank", "shift.litres_match_meters"):
        assert key in by_key, key
    assert body["summary"]["failed"] == 0, [r["sentence"] for r in body["results"] if r["status"] == "fail"]
    totals = by_key["report.shift_total_equals_total_sale"]
    assert len(totals) == 2 and all(t["status"] == "pass" and t["expected"] == t["actual"] for t in totals)
    # the dip on MS-22 is 40 L under book: within 0.5% so a warning, not a failure; and expenses await approval
    dip = next(r for r in by_key["report.dip_matches_total_stock"] if "MS-22" in r["sentence"])
    assert dip["status"] == "warn" and dip["difference"] == "-40.000"
    assert all(r["status"] == "warn" for r in by_key["report.shift_expenses_approved"] if r["actual"] != "0")
    bowser = by_key["report.bowser_meter_equals_bills"][0]
    assert bowser["status"] == "pass" and bowser["actual"] == "400.000"


def test_a_wrong_payment_total_makes_the_shift_check_fail_in_front_of_the_owner(client, day, manager, owner):
    s1 = day["shifts"][0]
    modes = {r["name"]: r["tender_id"] for r in client.get(f"/api/shift-totals/{s1['id']}", headers=manager).json()}
    r = client.put(f"/api/shift-totals/{s1['id']}/{modes['Paytm']}", headers=manager, json={"amount": "29000.00", "reason": "re-typed"})
    assert r.status_code == 200
    body, by_key = _keyed(client, owner)  # the save ran the checks: nobody pressed anything
    bad = next(t for t in by_key["report.shift_total_equals_total_sale"] if t["scope_id"] == s1["id"])
    assert bad["status"] == "fail" and bad["expected"] == "145000.00" and bad["actual"] == "144000.00" and bad["difference"] == "-1000.00"
    assert body["results"][0]["status"] == "fail"
    assert any(l["route"].startswith("/daily-report") for l in bad["links"])
    # putting the right figure back supersedes it; the failure stays in the history
    client.put(f"/api/shift-totals/{s1['id']}/{modes['Paytm']}", headers=manager, json={"amount": "30000.00", "reason": "fixed"})
    _, again = _keyed(client, owner)
    assert next(t for t in again["report.shift_total_equals_total_sale"] if t["scope_id"] == s1["id"])["status"] == "pass"
    hist = client.get(f"/api/checks/history?day={TODAY}", headers=owner).json()
    assert any(h["key"] == "report.shift_total_equals_total_sale" and h["status"] == "fail" for h in hist)


def test_bowser_meter_that_disagrees_with_the_bills_fails(client, day, manager, owner):
    r = client.post("/api/bowser/meter", headers=manager, json={"day": TODAY, "start_reading": "1000.000", "testing": "0", "end_reading": "1390.000"})
    assert r.status_code == 201
    _, by_key = _keyed(client, owner)
    meter = by_key["report.bowser_meter_equals_bills"][0]
    assert meter["status"] == "fail" and meter["difference"] == "-10.000"


def test_export_html_for_the_pdf_check(client, day, manager, tmp_path):
    """Used by the Electron end-to-end test (desktop/e2e/daily-report.spec.ts): writes the real report HTML to a
    file when PPERP_REPORT_HTML_OUT is set, so Chromium can print it to a PDF and count the pages."""
    import os

    out = os.environ.get("PPERP_REPORT_HTML_OUT")
    html = _report(client, manager)["html"]
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
    assert html.count('class="page"') == 2

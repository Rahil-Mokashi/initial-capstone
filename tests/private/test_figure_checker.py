"""Proves the figure checker on a SYNTHETIC sheet (always runs) and runs it on the owner's real figures when present.

private_samples/ is gitignored and absent on most machines: the real-data test then skips cleanly.
"""

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from figure_check import check_figures

REAL = Path(__file__).resolve().parents[2] / "private_samples" / "sample_daily_report_figures.md"


def synthetic(**overrides):
    base = {
        "shifts": [
            {
                "lines": {"CreditSale": "1000.00", "CARD": "0", "Expenses": "100.00", "Advance": "400.00", "Final": "500.00"},
                "printed_total": "2000.00", "grid_total_sale": "2000.00", "grid_oil": "300.00",
                "expenses": ["60.00", "40.00"], "printed_expenses_total": "100.00",
                "credit_sales": ["600.00", "400.00"], "printed_credit_total": "1000.00",
                "cash_book": {"receipts": ["0", "400.00", "500.00"], "payments": ["700.00", "200.00"],
                              "printed_receipts_total": "900.00", "printed_payments_total": "900.00"},
            },
        ],
        "oil": [{"name": "Racer", "opening": "10", "purchase": "5", "sale": "3", "balance": "12", "rate": "100.00", "total": "300.00", "shift": 1}],
        "grid": {"tanks": {"MS-22": {"os": "1000", "purchase": "500", "shift1": "300", "shift2": "200", "testing": "5",
                                      "total_stock": "1000", "closing": "990", "plus_minus": "-10"}},
                 "total_rs": "1700.00"},
        "bowser": {"stock_lines": [{"litres": "100", "rupees": "9000.00"}, {"litres": "50", "rupees": "4500.00"}],
                   "printed_stock_litres": "150", "printed_stock_rupees": "13500.00",
                   "bills": [{"no": "1", "qty": "40", "amount": "3800.00", "transport": "100.00", "total": "3900.00"}],
                   "printed_bills_qty": "40", "printed_closing_litres": "110",
                   "meter": {"start": "10", "testing": "0", "end": "50", "net": "40"}},
    }
    base.update(overrides)
    return base


def test_a_consistent_sheet_has_no_findings():
    assert check_figures(synthetic()) == []


def test_every_kind_of_printed_total_is_actually_checked():
    s = synthetic()
    s["shifts"][0]["printed_total"] = "2000.227"
    s["shifts"][0]["printed_expenses_total"] = "90.00"
    s["bowser"]["meter"]["net"] = "39"
    s["grid"]["tanks"]["MS-22"]["total_stock"] = "1001"  # testing must not be added back; this is just wrong
    keys = {f.key for f in check_figures(s)}
    assert {"shift1.transaction_total", "shift1.expenses_total", "bowser.meter_net", "bowser.meter_net_vs_bills",
            "grid.MS-22.total_stock"} <= keys


def test_a_rounding_gap_is_reported_with_its_size_and_never_hidden():
    s = synthetic()
    s["shifts"][0]["lines"]["CreditSale"] = "1000.227"
    s["shifts"][0]["credit_sales"] = ["600.227", "400.00"]
    s["shifts"][0]["printed_credit_total"] = "1000.227"
    s["shifts"][0]["printed_total"] = "2000.227"
    gaps = {f.key: f.gap for f in check_figures(s)}
    assert gaps == {"shift1.transaction_total_vs_grid_total_sale": Decimal("-0.227")}  # 2000.00 printed in the grid


@pytest.mark.skipif(not REAL.exists(), reason="private_samples/ is not on this machine (it is never committed)")
def test_real_figures_match_except_the_listed_oddities():
    text = REAL.read_text(encoding="utf-8")
    block = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
    if block is None:
        pytest.skip("the figures file has no ```json block yet; see tests/private/README.md for the layout")
    figures = json.loads(block.group(1))
    found = {f.key: f for f in check_figures(figures)}
    expected_oddities = set(figures.get("known_oddities", []))
    unexpected = set(found) - expected_oddities
    assert not unexpected, {k: (str(found[k].printed), str(found[k].computed)) for k in unexpected}
    # The oddities must still be visible: the real data is never "fixed" to make them disappear.
    assert expected_oddities <= set(found), f"listed as odd but now consistent: {expected_oddities - set(found)}"

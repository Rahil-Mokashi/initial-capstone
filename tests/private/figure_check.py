"""Checks the arithmetic of a daily report's printed figures against the owner's formulas.

The same checker runs on (a) a synthetic sheet in tests/private/test_figure_checker.py, always, and
(b) the owner's real, hand-verified figures in private_samples/ (never committed), when present.

Figures arrive as a dict (the real file carries it as a ```json block; see tests/private/README.md).
Numbers are strings. Every printed total is recomputed; a mismatch is reported as a Finding. Findings
the figures file lists under "known_oddities" are EXPECTED (they are the sheet's own quirks, e.g. the
3-decimal credit total, or a misread digit) and the test asserts they are still visible, never "fixed".
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import List

D = Decimal


@dataclass(frozen=True)
class Finding:
    key: str
    printed: Decimal
    computed: Decimal

    @property
    def gap(self) -> Decimal:
        return self.printed - self.computed


def _sum(values) -> Decimal:
    return sum((D(v) for v in values), D("0"))


def check_figures(f: dict) -> List[Finding]:
    """Every place where a printed total differs from the sum of its printed parts."""
    out: List[Finding] = []

    def compare(key, printed, computed):
        if printed is not None and D(printed) != computed:
            out.append(Finding(key, D(printed), computed))

    for i, s in enumerate(f.get("shifts", []), start=1):
        p = f"shift{i}"
        compare(f"{p}.transaction_total", s.get("printed_total"), _sum(s["lines"].values()))
        compare(f"{p}.transaction_total_vs_grid_total_sale", s.get("grid_total_sale"), _sum(s["lines"].values()))
        compare(f"{p}.expenses_total", s.get("printed_expenses_total"), _sum(s.get("expenses", [])))
        compare(f"{p}.credit_total", s.get("printed_credit_total"), _sum(s.get("credit_sales", [])))
        compare(f"{p}.credit_vs_transaction_line", s["lines"].get("CreditSale"), _sum(s.get("credit_sales", [])))
        compare(f"{p}.expenses_vs_transaction_line", s["lines"].get("Expenses"), _sum(s.get("expenses", [])))
        cb = s.get("cash_book")
        if cb:
            compare(f"{p}.cash_receipts_total", cb.get("printed_receipts_total"), _sum(cb["receipts"]))
            compare(f"{p}.cash_payments_total", cb.get("printed_payments_total"), _sum(cb["payments"]))
            compare(f"{p}.cash_book_sides_equal", cb.get("printed_receipts_total"), _sum(cb["payments"]))
        oil = _sum(r["total"] for r in f.get("oil", []) if r.get("shift") == i)
        compare(f"{p}.oil_vs_grid", s.get("grid_oil"), oil)

    for r in f.get("oil", []):
        compare(f"oil.{r['name']}.balance", r.get("balance"), D(r["opening"]) + D(r["purchase"]) - D(r["sale"]))
        compare(f"oil.{r['name']}.total", r.get("total"), (D(r["sale"]) * D(r["rate"])).quantize(D("0.01")))

    g = f.get("grid")
    if g:
        for code, t in g.get("tanks", {}).items():
            computed = D(t["os"]) + D(t["purchase"]) - D(t["shift1"]) - D(t["shift2"])
            compare(f"grid.{code}.total_stock", t.get("total_stock"), computed)  # testing is NOT added back
            if t.get("closing") is not None:
                compare(f"grid.{code}.plus_minus", t.get("plus_minus"), D(t["closing"]) - D(t["total_stock"]))
        total_sale = _sum(s["grid_total_sale"] for s in f["shifts"] if s.get("grid_total_sale"))
        oil = _sum(s["grid_oil"] for s in f["shifts"] if s.get("grid_oil"))
        compare("grid.total_rs", g.get("total_rs"), total_sale - oil)

    b = f.get("bowser")
    if b:
        compare("bowser.stock_total_litres", b.get("printed_stock_litres"), _sum(l["litres"] for l in b["stock_lines"]))
        compare("bowser.stock_total_rupees", b.get("printed_stock_rupees"), _sum(l["rupees"] for l in b["stock_lines"]))
        bills = b.get("bills", [])
        for x in bills:
            compare(f"bowser.bill.{x['no']}.total", x.get("total"), D(x["amount"]) + D(x["transport"]))
        qty = _sum(x["qty"] for x in bills)
        compare("bowser.bills_qty", b.get("printed_bills_qty"), qty)
        compare("bowser.closing_litres", b.get("printed_closing_litres"), _sum(l["litres"] for l in b["stock_lines"]) - qty)
        m = b.get("meter")
        if m:
            compare("bowser.meter_net", m.get("net"), D(m["end"]) - D(m["start"]) - D(m["testing"]))
            compare("bowser.meter_net_vs_bills", m.get("net"), qty)
    return out

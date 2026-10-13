"""Lays a DailyReport out as printable HTML: two sides of A4, the old report's sections in its order.

Pure formatting (no database, no permissions). The same layout serves Classic and Plus; Plus passes
`extras` (a checks strip, bank status, dip percentage, credit summary, signature lines) and the
renderer slots them in without changing the order of the Classic sections.
"""

from contextvars import ContextVar
from decimal import Decimal
from html import escape
from typing import Optional

from app.services.daily_report_service import DailyReport

_Z = Decimal("0")

CSS = """
<style>
@page { size: A4; margin: 8mm; }
.dr { font-family: Arial, Helvetica, sans-serif; font-size: 8.5pt; color: #000; }
.dr .page { page-break-after: always; }
.dr .page:last-child { page-break-after: auto; }
.dr h1 { font-size: 13pt; margin: 0; text-align: center; }
.dr h2 { font-size: 9.5pt; margin: 6px 0 2px; }
.dr .sub { text-align: center; margin: 0 0 4px; font-size: 8pt; }
.dr table { border-collapse: collapse; width: 100%; margin-bottom: 4px; }
.dr th, .dr td { border: 0.6pt solid #000; padding: 1.5px 4px; }
.dr th { background: #e8e8e8; text-align: left; }
.dr td.n, .dr th.n { text-align: right; white-space: nowrap; }
.dr tr.t td, .dr tr.t th { font-weight: bold; background: #f3f3f3; }
.dr .cols { display: flex; gap: 8px; }
.dr .cols > div { flex: 1; min-width: 0; }
.dr .strip { border: 1pt solid #000; padding: 3px 6px; margin: 4px 0; font-weight: bold; }
.dr .bad { color: #a00000; }
.dr .sign { display: flex; justify-content: space-between; margin-top: 18px; }
.dr .sign span { border-top: 0.6pt solid #000; padding-top: 2px; min-width: 40%; text-align: center; }
.dr .foot { font-size: 7pt; text-align: center; margin-top: 6px; }
</style>
"""


def _group(int_digits: str) -> str:
    if len(int_digits) <= 3:
        return int_digits
    head, tail = int_digits[:-3], int_digits[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail


# 'classic' prints exactly as the old report; 'plus' adds the rupee sign and fixed two-place litres. Set only inside
# render_daily_report, so every other caller (bank check sentences, statements) always gets the classic form.
_STYLE: ContextVar[str] = ContextVar("daily_report_style", default="classic")


def inr(value: Optional[Decimal], places: int = 2) -> str:
    """12,34,567.89 - the Indian digit grouping the old report uses. None prints as blank."""
    if value is None:
        return ""
    text = f"{abs(value):.{places}f}"
    whole, _, frac = text.partition(".")
    out = _group(whole) + (f".{frac}" if frac else "")
    out = f"-{out}" if value < 0 and Decimal(text) != 0 else out
    return ("₹" + out if not out.startswith("-") else "-₹" + out[1:]) if _STYLE.get() == "plus" else out


def litres(value: Optional[Decimal]) -> str:
    """Litres with up to three decimals and no trailing zeros (35,485 / 13,477.25), as the old report prints them."""
    if value is None:
        return ""
    text = f"{abs(value):.2f}" if _STYLE.get() == "plus" else f"{abs(value):.3f}".rstrip("0").rstrip(".")
    whole, _, frac = text.partition(".")
    out = _group(whole) + (f".{frac}" if frac else "")
    return f"-{out}" if value < 0 and Decimal(text) != 0 else out


def signed_litres(value: Optional[Decimal]) -> str:
    if value is None:
        return ""
    s = litres(value)
    return f"+{s}" if value > 0 else s


def _e(text) -> str:
    return escape(str(text if text is not None else ""))


def _cells(values, cls="n"):
    return "".join(f'<td class="{cls}">{v}</td>' for v in values)


def render_daily_report(report: DailyReport, company=None, extras: Optional[dict] = None) -> str:
    extras = extras or {}
    title = extras.get("title", "DAILY REPORT")
    token = _STYLE.set(extras.get("style", "classic"))
    try:
        return f'{CSS}<div class="dr">{_front(report, company, title, extras)}{_back(report, extras)}</div>'
    finally:
        _STYLE.reset(token)


# ----------------------------------------------------------------------------------------- FRONT
def _front(r: DailyReport, company, title: str, extras: dict) -> str:
    name = _e(getattr(company, "company_name", None) or "Petrol Pump") if company is not None else "Petrol Pump"
    parts = [
        '<div class="page">',
        f"<h1>{name} &mdash; {_e(title)}</h1>",
        f'<p class="sub">Date: {r.day.strftime("%d-%m-%Y")}</p>',
        extras.get("strip_html", ""),
        _sale_details(r, extras),
        '<div class="cols">',
    ]
    for s in r.shifts[:2]:
        parts.append(f"<div>{_transactions(s, extras)}</div>")
    parts.append("</div>")
    parts.append('<div class="cols">')
    for s in r.shifts[:2]:
        parts.append(f"<div>{_cash_book(s)}</div>")
    parts.append("</div>")
    parts.append('<div class="cols">')
    for s in r.shifts[:2]:
        parts.append(f"<div>{_credit_sales(s)}</div>")
    parts.append("</div>")
    parts.append(extras.get("front_extra_html", ""))
    parts.append(extras.get("footer_html", "").replace("{page}", "1"))
    parts.append("</div>")
    return "".join(parts)


def _sale_details(r: DailyReport, extras: dict) -> str:
    head = "".join(f'<th class="n">{_e(c.code)}</th>' for c in r.tanks)
    ids = [c.tank_id for c in r.tanks]

    def row(label, per_tank, fmt, total=None, oil="", sale=""):
        cells = "".join(f'<td class="n">{fmt(per_tank.get(t)) if per_tank.get(t) is not None else ""}</td>' for t in ids)
        tot = fmt(total) if total is not None else ""
        return f'<tr><td>{label}</td>{cells}<td class="n">{tot}</td><td class="n">{oil}</td><td class="n">{sale}</td></tr>'

    def sum_of(d):
        vals = [d.get(t) for t in ids if d.get(t) is not None]
        return sum(vals, _Z) if vals else None

    rows = [
        row("O/S", r.opening, litres, sum_of(r.opening)),
        row("Purchase", r.purchase, litres, sum_of(r.purchase)),
    ]
    for s in r.shifts:
        rows.append(row(f"Shift{s.number}", s.litres_by_tank if s.shift_id else {}, litres,
                        sum_of(s.litres_by_tank) if s.shift_id else None,
                        inr(s.oil_rs) if s.shift_id else "", inr(s.total_sale) if s.shift_id else ""))
    rows += [
        row("Testing", r.testing, litres, sum_of(r.testing)),
        row("Total Stock", r.total_stock, litres, sum_of(r.total_stock)),
        row("(+/-)", r.plus_minus, signed_litres, sum_of(r.plus_minus) if any(v is not None for v in r.plus_minus.values()) else None),
        row("Closing Stock", r.closing, litres, sum_of(r.closing)),
    ]
    extra_cols = len(ids) + 4
    rows.append(
        f'<tr class="t"><td>Total Rs</td><td colspan="{extra_cols - 1}"></td><td class="n">{inr(r.total_rs)}</td></tr>'
    )
    return (
        "<h2>Sale Details</h2><table>"
        f'<tr><th></th>{head}<th class="n">Total</th><th class="n">Oil</th><th class="n">Total Sale</th></tr>'
        + "".join(rows)
        + "</table>"
        + extras.get("grid_extra_html", "")
    )


def _transactions(s, extras: dict) -> str:
    bank = extras.get("bank_status", {})
    rows = []
    for label, amount in s.lines:
        status = bank.get((s.number, label), "")
        rows.append(f'<tr><td>{_e(label)}{(" <small>" + _e(status) + "</small>") if status else ""}</td><td class="n">{inr(amount)}</td></tr>')
    rows.append(f'<tr class="t"><td>Total</td><td class="n">{inr(s.lines_total) if s.shift_id else ""}</td></tr>')
    return f"<h2>Shift {s.number} Transaction Details</h2><table>" + "".join(rows) + "</table>"


def _cash_book(s) -> str:
    receipts = [("Opening Balance", s.opening_balance), ("Advance", s.advance), ("Final", s.final)] + list(s.other_receipts)
    payments = list(s.deposits) + [("Cash in hand", s.cash_in_hand)]
    n = max(len(receipts), len(payments))
    receipts += [("", None)] * (n - len(receipts))
    payments += [("", None)] * (n - len(payments))
    body = "".join(
        f"<tr><td>{_e(a)}</td><td class='n'>{inr(x) if a else ''}</td><td>{_e(b)}</td><td class='n'>{inr(y) if b else ''}</td></tr>"
        for (a, x), (b, y) in zip(receipts, payments)
    )
    total = (
        f'<tr class="t"><td>Total</td><td class="n">{inr(s.receipts_total) if s.shift_id else ""}</td>'
        f'<td>Total</td><td class="n">{inr(s.payments_total) if s.shift_id else ""}</td></tr>'
    )
    return (
        f"<h2>Shift {s.number} Cash Book</h2><table>"
        '<tr><th>Cash Receipt</th><th class="n">Amount</th><th>Cash Payment</th><th class="n">Amount</th></tr>'
        + body + total + "</table>"
    )


def _credit_sales(s) -> str:
    rows = "".join(
        f"<tr><td>{_e(no)}</td><td>{_e(name)}</td><td class='n'>{inr(amount)}</td><td></td></tr>"
        for no, name, amount in s.credit_sales
    )
    total = f'<tr class="t"><td colspan="3">Total</td><td class="n">{inr(s.credit_total) if s.shift_id else ""}</td></tr>'
    return (
        f"<h2>Shift {s.number} Credit Sale</h2><table>"
        '<tr><th>Bill No</th><th>Name</th><th class="n">Amount</th><th class="n">Total</th></tr>'
        + rows + total + "</table>"
    )


# ----------------------------------------------------------------------------------------- BACK
def _back(r: DailyReport, extras: dict) -> str:
    parts = ['<div class="page">', f'<h1>{_e(extras.get("title", "DAILY REPORT"))} &mdash; {r.day.strftime("%d-%m-%Y")} (back)</h1>']
    parts.append("<h2>Expenses Details</h2><div class='cols'>")
    for s in r.shifts[:2]:
        rows = "".join(f"<tr><td>{_e(t)}</td><td class='n'>{inr(a)}</td><td></td></tr>" for t, a in s.expenses)
        total = f'<tr class="t"><td colspan="2">Total</td><td class="n">{inr(s.expenses_total) if s.shift_id else ""}</td></tr>'
        parts.append(
            f"<div><table><tr><th colspan='3'>Shift {s.number}</th></tr>"
            "<tr><th>Details</th><th class='n'>Amount</th><th class='n'>Total</th></tr>" + rows + total + "</table></div>"
        )
    parts.append("</div>")
    parts.append(_oil(r))
    parts.append(_bowser(r, extras))
    parts.append(extras.get("back_extra_html", ""))
    parts.append(extras.get("footer_html", "").replace("{page}", "2"))
    parts.append("</div>")
    return "".join(parts)


def _oil(r: DailyReport) -> str:
    rows = "".join(
        f"<tr><td>{_e(o.name)}</td><td class='n'>{litres(o.opening)}</td><td class='n'>{litres(o.purchase)}</td>"
        f"<td class='n'>{litres(o.sale)}</td><td class='n'>{litres(o.balance)}</td><td class='n'>{inr(o.rate)}</td>"
        f"<td class='n'>{inr(o.total)}</td><td>{_e(o.shift_label)}</td><td>{_e(o.customer)}</td></tr>"
        for o in r.oil_rows
    )
    return (
        "<h2>Oil Sale</h2><table><tr><th>Name</th><th class='n'>Opening</th><th class='n'>Purchase</th><th class='n'>Sale</th>"
        "<th class='n'>Balance</th><th class='n'>Rate</th><th class='n'>Total</th><th>Shift</th><th>Customer</th></tr>"
        + rows + "</table>"
    )


def _bowser(r: DailyReport, extras: dict) -> str:
    b = r.bowser
    if b is None:
        return ""
    a_rows = "".join(
        f"<tr><td>{_e(l.label)}</td><td class='n'>{litres(l.litres)}</td><td class='n'>{inr(l.rupees)}</td></tr>"
        for l in b.stock_lines
    )
    a = (
        "<table><tr><th>A] Internal stock</th><th class='n'>Ltr</th><th class='n'>Rs</th></tr>" + a_rows
        + f"<tr class='t'><td>Total</td><td class='n'>{litres(b.stock_litres)}</td><td class='n'>{inr(b.stock_rupees)}</td></tr></table>"
    )
    bills = "".join(
        f"<tr><td>{_e(x.bill_no)}</td><td>{_e(x.customer.name if x.customer else '')}</td><td class='n'>{litres(x.quantity)}</td>"
        f"<td class='n'>{inr(x.amount)}</td><td class='n'>{inr(x.transport)}</td><td class='n'>{inr(x.total)}</td></tr>"
        for x in b.bills
    )
    bt = (
        f"<tr class='t'><td colspan='2'>Total</td><td class='n'>{litres(b.bills_qty)}</td><td class='n'>{inr(b.bills_amount)}</td>"
        f"<td class='n'>{inr(b.bills_transport)}</td><td class='n'>{inr(b.bills_total)}</td></tr>"
        f"<tr class='t'><td colspan='2'>Closing Stock</td><td class='n'>{litres(b.closing_litres)}</td>"
        f"<td class='n'>{inr(b.closing_rupees)}</td><td></td><td></td></tr>"
    )
    bb = (
        "<table><tr><th>B] Bill No</th><th>Cust Name</th><th class='n'>Qty</th><th class='n'>Amount</th>"
        "<th class='n'>Transport</th><th class='n'>Total</th></tr>" + bills + bt + "</table>"
    )
    m = b.meter
    c = (
        "<table><tr><th colspan='2'>C] Bowser meter</th></tr>"
        f"<tr><td>Start Reading</td><td class='n'>{litres(m.start_reading) if m else ''}</td></tr>"
        f"<tr><td>Testing</td><td class='n'>{litres(m.testing) if m else ''}</td></tr>"
        f"<tr><td>End Reading</td><td class='n'>{litres(m.end_reading) if m else ''}</td></tr>"
        f"<tr class='t'><td>Net Sale</td><td class='n'>{litres(b.meter_net) if b.meter_net is not None else ''}</td></tr></table>"
    )
    return f"<h2>Bowser Van</h2>{a}{bb}{c}{extras.get('bowser_extra_html', '')}"

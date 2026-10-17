"""The owner's two-sided daily report, as data.

Everything the Classic report prints is computed here from the database, and nothing here is typed in
by hand. The formulas are the owner's own (docs/daily-report-spec.md, docs/daily-report-gap-analysis.md):

  Total Stock   = O/S + Purchase - Shift1 - Shift2          (testing shown, NOT added back; T-01 setting)
  (+/-)         = Closing Stock (dip) - Total Stock
  Total Rs      = sum of shift Total Sale - sum of Oil       (fuel-only rupees)
  Shift Total   = CreditSale + CARD + DTP Card + Other + PHONE PAY + PTM + Expenses + Advance + Final
                  and it must equal the shift's Total Sale (a check, not an assumption)
  Oil Balance   = Opening + Purchase - Sale ;  Oil Total = Sale x Rate
  Bowser        = see BowserService

The renderer (daily_report_html.py) only lays this out; the checks (report_checks.py) re-verify it.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from app.core.constants import PaymentMethod, Permission, SaleStatus
from app.core.dates import local_day_bounds_utc
from app.core.money import money, volume
from app.core.permissions import require_permission
from app.services.bowser_service import BowserDay
from app.services.tender_entry_service import REPORT_ORDER, report_label

_Z = Decimal("0")


@dataclass
class TankCol:
    tank_id: str
    code: str


@dataclass
class OilRow:
    name: str
    opening: Decimal
    purchase: Decimal
    sale: Decimal
    balance: Decimal
    rate: Decimal
    total: Decimal
    shift_label: str
    customer: str
    item_id: str = ""


@dataclass
class ShiftBlock:
    number: int  # 1-based position in the day
    shift_id: Optional[str]
    label: str
    litres_by_tank: Dict[str, Decimal] = field(default_factory=dict)
    unassigned_litres: Decimal = _Z
    fuel_rs: Decimal = _Z
    oil_rs: Decimal = _Z
    total_sale: Decimal = _Z
    # Transaction details, in print order: (label, amount)
    lines: List[tuple] = field(default_factory=list)
    lines_total: Decimal = _Z
    credit_by_tender_rs: Decimal = _Z  # the same credit total reached through Sale.tender_id (cross-check)
    # Cash book
    opening_balance: Decimal = _Z
    advance: Decimal = _Z
    final: Decimal = _Z
    other_receipts: List[tuple] = field(default_factory=list)  # (details, amount)
    deposits: List[tuple] = field(default_factory=list)  # (bank name, amount)
    cash_in_hand: Decimal = _Z
    receipts_total: Decimal = _Z
    payments_total: Decimal = _Z
    has_cash_book: bool = False
    # Credit sales: (bill no, name, amount)
    credit_sales: List[tuple] = field(default_factory=list)
    credit_total: Decimal = _Z
    # Expenses: (details, amount) and how many are still waiting for approval
    expenses: List[tuple] = field(default_factory=list)
    expenses_total: Decimal = _Z
    pending_expenses: int = 0


@dataclass
class DailyReport:
    day: date
    tanks: List[TankCol]
    shifts: List[ShiftBlock]
    opening: Dict[str, Decimal] = field(default_factory=dict)
    purchase: Dict[str, Decimal] = field(default_factory=dict)
    testing: Dict[str, Decimal] = field(default_factory=dict)
    total_stock: Dict[str, Decimal] = field(default_factory=dict)
    closing: Dict[str, Optional[Decimal]] = field(default_factory=dict)  # dip; None = not measured
    plus_minus: Dict[str, Optional[Decimal]] = field(default_factory=dict)
    tank_book_end: Dict[str, Decimal] = field(default_factory=dict)  # the tank's own book at the end of the day
    total_rs: Decimal = _Z  # fuel-only rupees
    oil_rows: List[OilRow] = field(default_factory=list)
    bowser: Optional[BowserDay] = None
    add_testing_back: bool = False
    rounding_rule: str = "per_bill"


class DailyReportService:
    def __init__(
        self, shift_repo, tank_repo, sale_repo, expense_repo, assignment_repo, query_repo, cash_book_service,
        tender_entries, lubricants, bowser, settings, uses_repo, auth_service, audit_repo=None,
    ):
        self._shifts = shift_repo
        self._tanks = tank_repo
        self._sales = sale_repo
        self._expenses = expense_repo
        self._assignments = assignment_repo
        self._q = query_repo
        self._cash = cash_book_service
        self._tenders = tender_entries
        self._lub = lubricants
        self._bowser = bowser
        self._settings = settings
        self._uses = uses_repo
        self._auth_service = auth_service
        self._audit_repo = audit_repo

    @require_permission(Permission.DAILY_REPORT_VIEW.value)
    def build(self, actor_user_id: str, day: date) -> DailyReport:
        return self.compute(day, actor_user_id)

    def compute(self, day: date, actor_user_id: str) -> DailyReport:
        """Also used by the checks, which must see the report whoever triggered them (they pass the saver's id)."""
        tanks = sorted(self._tanks.list_all(), key=lambda t: (t.created_at, t.code))
        cols = [TankCol(t.id, t.code) for t in tanks]
        shifts = self._q.shifts_on(day)
        add_testing = self._settings.get("add_testing_back") == "on"
        rule = self._settings.get("rounding_rule")
        report = DailyReport(day=day, tanks=cols, shifts=[], add_testing_back=add_testing, rounding_rule=rule)

        start, end = local_day_bounds_utc(day)
        for tank in tanks:
            txs = self._q.tank_transactions_since(tank.id, start)
            after_start = sum((t.quantity for t in txs), _Z)
            report.opening[tank.id] = volume(tank.current_stock - after_start)
            in_day = [t for t in txs if t.transaction_at <= end]
            report.purchase[tank.id] = volume(sum((t.quantity for t in in_day if t.transaction_type == "receipt"), _Z))
            report.tank_book_end[tank.id] = volume(report.opening[tank.id] + sum((t.quantity for t in in_day), _Z))
            readings = self._q.tank_readings_between(tank.id, start, end)
            if readings:
                report.closing[tank.id] = volume(readings[-1].physical_stock)
            else:
                rec = self._q.fuel_reconciliation_for(tank.id, day)
                report.closing[tank.id] = volume(rec.physical_stock) if rec is not None else None

        oil_by_shift: Dict[str, List[OilRow]] = {}
        report.oil_rows, oil_by_shift = self._oil_rows(day, shifts, rule)

        for i in range(max(2, len(shifts))):
            shift = shifts[i] if i < len(shifts) else None
            report.shifts.append(self._shift_block(i + 1, shift, cols, oil_by_shift, actor_user_id, rule))

        report.testing = {c.tank_id: _Z for c in cols}
        for shift in shifts:
            for a in self._assignments.list_for_shift(shift.id):
                tid = a.nozzle.tank_id if a.nozzle is not None else None
                if tid in report.testing:
                    report.testing[tid] += a.testing_volume
        for c in cols:
            sold = sum((s.litres_by_tank.get(c.tank_id, _Z) for s in report.shifts), _Z)
            total = report.opening[c.tank_id] + report.purchase[c.tank_id] - sold
            if add_testing:
                total += report.testing[c.tank_id]
            report.total_stock[c.tank_id] = volume(total)
            dip = report.closing[c.tank_id]
            report.plus_minus[c.tank_id] = volume(dip - report.total_stock[c.tank_id]) if dip is not None else None

        report.total_rs = money(sum((s.total_sale for s in report.shifts), _Z) - sum((s.oil_rs for s in report.shifts), _Z))
        report.bowser = self._bowser.build_day(day)
        return report

    # -- pieces -------------------------------------------------------------------------------------------
    def _oil_rows(self, day, shifts, rule):
        """One row per item per shift sold, with the running balance after it. Opening/Purchase shown on an item's first row."""
        by_shift_id = {s.id: (i + 1) for i, s in enumerate(shifts)}
        moves = self._lub.day_movements(day)
        items: Dict[str, list] = {}
        for m in moves:
            items.setdefault(m.item_id, []).append(m)
        rows: List[OilRow] = []
        per_shift: Dict[str, List[OilRow]] = {}
        for item_id, ms in items.items():
            item = ms[0].item
            opening = self._lub.balance_before(item_id, day)
            purchase = sum((m.quantity for m in ms if m.kind in ("purchase", "opening", "adjustment")), _Z)
            running = opening + purchase
            sales = [m for m in ms if m.kind == "sale"]
            grouped: Dict[tuple, list] = {}
            for m in sales:
                grouped.setdefault((m.shift_id, m.unit_rate, m.customer_name or ""), []).append(m)
            first = True
            if not sales and (opening or purchase):
                rows.append(OilRow(item.name, opening, purchase, _Z, running, item.default_rate, _Z, "", "", item_id))
                continue
            for (shift_id, rate, customer), group in grouped.items():
                qty = sum((m.quantity for m in group), _Z)
                total = money(sum((m.amount for m in group), _Z))
                running -= qty
                n = by_shift_id.get(shift_id)
                row = OilRow(
                    item.name, opening if first else _Z, purchase if first else _Z, qty, running, rate, total,
                    f"Shift {n}" if n else "", customer, item_id,
                )
                first = False
                rows.append(row)
                if shift_id:
                    per_shift.setdefault(shift_id, []).append(row)
        return rows, per_shift

    def _shift_block(self, number, shift, cols, oil_by_shift, actor_user_id, rule) -> ShiftBlock:
        if shift is None:
            block = ShiftBlock(number=number, shift_id=None, label=f"Shift {number}")
            block.lines = self._line_labels_zero()
            return block
        block = ShiftBlock(number=number, shift_id=shift.id, label=f"Shift {number}")
        sales = [s for s in self._sales.list_by_shift(shift.id) if s.status == SaleStatus.COMPLETED.value]
        for c in cols:
            block.litres_by_tank[c.tank_id] = _Z
        credit_rows = []
        for s in sales:
            tid = s.nozzle.tank_id if s.nozzle is not None else None
            if tid in block.litres_by_tank:
                block.litres_by_tank[tid] += s.quantity
            else:
                block.unassigned_litres += s.quantity
            block.fuel_rs += s.amount
            if s.payment_method == PaymentMethod.CREDIT.value:
                credit_rows.append((s.receipt_number, (s.customer.name if s.customer else "") + (f" ({s.vehicle_number})" if s.vehicle_number else ""), s.amount))
                block.credit_total += s.amount
            if s.tender is not None and s.tender.settlement_type == "invoiced_credit":
                block.credit_by_tender_rs += s.amount
        block.litres_by_tank = {k: volume(v) for k, v in block.litres_by_tank.items()}
        block.credit_sales = credit_rows
        block.fuel_rs = money(block.fuel_rs)
        block.credit_total = money(block.credit_total)

        oil_rows = oil_by_shift.get(shift.id, [])
        raw_oil = sum((r.sale * r.rate for r in oil_rows), _Z)
        block.oil_rs = money(raw_oil) if rule == "per_total" else money(sum((r.total for r in oil_rows), _Z))
        block.total_sale = money(block.fuel_rs + block.oil_rs)

        expenses = [e for e in self._expenses.list_by_shift(shift.id) if e.status != "rejected"]
        for e in sorted(expenses, key=lambda e: e.created_at):
            text = (e.description or (e.category.name if getattr(e, "category", None) else "Expense")).strip()
            block.expenses.append((text, e.amount))
            if e.status == "pending":
                block.pending_expenses += 1
        block.expenses_total = money(sum((a for _, a in block.expenses), _Z))

        typed = self._tenders.totals_for_shift(shift.id)
        names = [n for n in REPORT_ORDER] + sorted(n for n in typed if n not in REPORT_ORDER)
        lines = [("CreditSale", block.credit_total)]
        for n in names:
            lines.append((report_label(n), money(typed.get(n, _Z))))
        lines.append(("Expenses", block.expenses_total))
        # Internal read: a verification must see the cash book whoever saved the data that triggered it, so the
        # service's RECONCILIATION_VIEW wrapper is bypassed here (build() itself is gated by DAILY_REPORT_VIEW).
        summary = self._cash.get_cash_book_summary.__wrapped__(self._cash, actor_user_id, shift.id)
        block.has_cash_book = summary.cash_book is not None
        block.opening_balance = summary.opening_balance
        block.advance = summary.cash_book.advance_amount if summary.cash_book else _Z
        block.final = summary.cash_book.final_amount if summary.cash_book else _Z
        lines.append(("Advance", block.advance))
        lines.append(("Final", block.final))
        block.lines = lines
        block.lines_total = money(sum((a for _, a in lines), _Z))

        block.other_receipts = [
            (f"cash short return ({self._employee_name(r)})", r.amount) for r in summary.shortage_recoveries
        ]
        block.deposits = [(d.bank_name, d.amount) for d in summary.bank_deposits]
        block.cash_in_hand = summary.closing_cash_in_hand
        block.receipts_total = money(
            block.opening_balance + block.advance + block.final + sum((a for _, a in block.other_receipts), _Z)
        )
        block.payments_total = money(sum((a for _, a in block.deposits), _Z) + block.cash_in_hand)
        return block

    @staticmethod
    def _employee_name(recovery) -> str:
        e = recovery.shortage.employee if recovery.shortage is not None else None
        return f"{e.first_name} {e.last_name}".strip() if e is not None else "employee"

    def _line_labels_zero(self):
        names = [report_label(n) for n in REPORT_ORDER]
        return [("CreditSale", _Z)] + [(n, _Z) for n in names] + [("Expenses", _Z), ("Advance", _Z), ("Final", _Z)]


def report_to_dict(obj):
    """Plain JSON-ready structure: Decimals as exact strings, dates as ISO, dataclasses as dicts."""
    import dataclasses
    from datetime import date as _date

    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: report_to_dict(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, Decimal):
        return format(obj, "f")
    if isinstance(obj, _date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): report_to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [report_to_dict(v) for v in obj]
    if obj is None or isinstance(obj, (str, int, bool)):
        return obj
    # ORM rows inside BowserDay (bills, meter): keep only what a screen needs
    if hasattr(obj, "bill_no"):
        return {
            "id": obj.id, "bill_no": obj.bill_no, "customer": obj.customer.name if obj.customer else "", "quantity": format(obj.quantity, "f"),
            "rate": format(obj.rate, "f"), "amount": format(obj.amount, "f"), "transport": format(obj.transport, "f"),
            "total": format(obj.total, "f"),
        }
    if hasattr(obj, "start_reading"):
        return {"start_reading": format(obj.start_reading, "f"), "testing": format(obj.testing, "f"), "end_reading": format(obj.end_reading, "f")}
    return str(obj)

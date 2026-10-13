"""A credit customer's money story, computed from their bills and payments: nothing is stored.

Bills are every credit sale at a shift plus every bowser bill (with transport). Payments are not tied to
a specific bill (that is how CustomerPayment has always worked), so they are applied oldest bill first
(FIFO): that gives each bill's outstanding amount, its age, the ageing buckets, the oldest unpaid bill and
the average days a bill took to be paid. These are pure functions so they can be tested without a database.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional, Tuple

_Z = Decimal("0")
BUCKETS = ("0-30", "31-60", "61-90", "90+")


@dataclass
class LedgerBill:
    kind: str  # "sale" (credit sale at a shift) | "bowser" (bowser delivery bill)
    ref: str  # receipt number / bill number
    bill_date: date
    amount: Decimal
    order: int = 0  # tie-break for bills on the same day: entry order
    vehicle_no: Optional[str] = None
    slip_no: Optional[str] = None
    sale_id: Optional[str] = None
    shift_id: Optional[str] = None
    # filled in by apply_payments
    paid: Decimal = _Z
    outstanding: Decimal = _Z
    age_days: int = 0
    days_to_pay: Optional[int] = None


@dataclass
class LedgerPayment:
    pay_date: date
    amount: Decimal
    method: str = ""
    reference: Optional[str] = None


@dataclass
class LedgerSummary:
    bills: List[LedgerBill]
    balance: Decimal  # total billed - total paid (negative = paid in advance)
    total_billed: Decimal
    total_paid: Decimal
    unapplied: Decimal  # payments beyond all bills
    largest_outstanding_ever: Decimal
    average_days_to_pay: Optional[Decimal]
    oldest_unpaid: Optional[LedgerBill]
    buckets: dict = field(default_factory=dict)


def bucket_of(age_days: int) -> str:
    if age_days <= 30:
        return BUCKETS[0]
    if age_days <= 60:
        return BUCKETS[1]
    if age_days <= 90:
        return BUCKETS[2]
    return BUCKETS[3]


def apply_payments(bills: List[LedgerBill], payments: List[LedgerPayment], as_of: date) -> LedgerSummary:
    ordered = sorted(bills, key=lambda b: (b.bill_date, b.order))
    pays = sorted(payments, key=lambda p: p.pay_date)
    total_paid = sum((p.amount for p in pays), _Z)
    pool = total_paid
    for b in ordered:
        applied = min(b.amount, pool)
        pool -= applied
        b.paid, b.outstanding = applied, b.amount - applied
        b.age_days = max(0, (as_of - b.bill_date).days)

    # days to pay: the day cumulative payments first covered everything billed up to and including this bill
    cum_bill = _Z
    cum_pay_points: List[Tuple[date, Decimal]] = []
    running = _Z
    for p in pays:
        running += p.amount
        cum_pay_points.append((p.pay_date, running))
    days: List[int] = []
    for b in ordered:
        cum_bill += b.amount
        if b.outstanding == 0:
            when = next((d for d, cum in cum_pay_points if cum >= cum_bill), None)
            if when is not None:
                b.days_to_pay = max(0, (when - b.bill_date).days)
                days.append(b.days_to_pay)

    # largest balance ever owed: replay the events in date order, bills before payments on the same day
    events = [(b.bill_date, 0, b.amount) for b in ordered] + [(p.pay_date, 1, -p.amount) for p in pays]
    level, peak = _Z, _Z
    for _, _, delta in sorted(events, key=lambda e: (e[0], e[1])):
        level += delta
        peak = max(peak, level)

    buckets = {name: _Z for name in BUCKETS}
    for b in ordered:
        if b.outstanding > 0:
            buckets[bucket_of(b.age_days)] += b.outstanding
    total_billed = sum((b.amount for b in ordered), _Z)
    unpaid = [b for b in ordered if b.outstanding > 0]
    avg = (Decimal(sum(days)) / Decimal(len(days))).quantize(Decimal("0.1")) if days else None
    return LedgerSummary(
        bills=ordered, balance=total_billed - total_paid, total_billed=total_billed, total_paid=total_paid,
        unapplied=pool, largest_outstanding_ever=peak, average_days_to_pay=avg,
        oldest_unpaid=unpaid[0] if unpaid else None, buckets=buckets,
    )


@dataclass
class StatementLine:
    line_date: date
    document: str
    vehicle_no: Optional[str]
    slip_no: Optional[str]
    debit: Decimal
    credit: Decimal
    balance: Decimal


def statement_lines(
    bills: List[LedgerBill], payments: List[LedgerPayment], date_from: date, date_to: date
) -> Tuple[Decimal, List[StatementLine], Decimal]:
    """(opening balance at date_from, the lines inside the range with a running balance, closing balance)."""
    events = [(b.bill_date, 0, b.order, b) for b in bills] + [(p.pay_date, 1, 0, p) for p in payments]
    opening = _Z
    lines: List[StatementLine] = []
    running = _Z
    for when, _, _, item in sorted(events, key=lambda e: (e[0], e[1], e[2])):
        is_bill = isinstance(item, LedgerBill)
        delta = item.amount if is_bill else -item.amount
        if when < date_from:
            opening += delta
            running = opening
            continue
        if when > date_to:
            break
        running += delta
        if is_bill:
            label = ("Bowser bill " if item.kind == "bowser" else "Bill ") + item.ref
            lines.append(StatementLine(when, label, item.vehicle_no, item.slip_no, item.amount, _Z, running))
        else:
            ref = f" ({item.reference})" if item.reference else ""
            lines.append(StatementLine(when, f"Payment received{ref}", None, None, _Z, item.amount, running))
    return opening, lines, running

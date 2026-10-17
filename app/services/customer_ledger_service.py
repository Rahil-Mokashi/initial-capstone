"""Read-side views of credit: one customer's history, the ageing of everyone, and statements.

Permission: CREDIT_VIEW, like the existing credit screens. Reads only; it changes nothing.
Bowser customers are credit customers too: their bills (with transport) are in the same history and
ageing. The internal "Stock Transfer (Bouser)" account is left out of the lists and totals the owners
chase, since nobody pays it.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional

from app.core.constants import PaymentMethod, Permission, SaleStatus
from app.core.dates import local_date_of
from app.core.exceptions import NotFoundError
from app.core.permissions import require_permission
from app.services.bowser_service import BOWSER_CUSTOMER_NAME
from app.services.customer_ledger import (
    BUCKETS,
    LedgerBill,
    LedgerPayment,
    LedgerSummary,
    StatementLine,
    apply_payments,
    statement_lines,
)

_Z = Decimal("0")


@dataclass
class CustomerView:
    customer_id: str
    name: str
    phone: Optional[str]
    credit_limit: Optional[Decimal]
    payment_due_days: Optional[int]
    summary: LedgerSummary
    payments: List[LedgerPayment]
    available: Optional[Decimal]
    overdue: bool
    overdue_days: int  # days past the due date of the oldest unpaid bill (0 when not overdue)
    as_of: date


@dataclass
class AgeingRow:
    customer_id: str
    name: str
    balance: Decimal
    buckets: dict
    oldest_unpaid_ref: Optional[str]
    oldest_unpaid_date: Optional[date]
    oldest_unpaid_age: Optional[int]
    credit_limit: Optional[Decimal]
    over_limit: bool
    overdue: bool


@dataclass
class AgeingReport:
    as_of: date
    rows: List[AgeingRow]
    totals: dict = field(default_factory=dict)
    total_balance: Decimal = _Z


@dataclass
class StatementView:
    customer_id: str
    name: str
    date_from: date
    date_to: date
    opening_balance: Decimal
    lines: List[StatementLine]
    closing_balance: Decimal
    bills: List[LedgerBill]  # bill-wise: every bill still relevant, with paid / outstanding / age as of date_to


class CustomerLedgerService:
    def __init__(self, customer_repo, account_repo, sale_repo, payment_repo, bowser_repo, detail_repo, auth_service):
        self._customers = customer_repo
        self._accounts = account_repo
        self._sales = sale_repo
        self._payments = payment_repo
        self._bowser = bowser_repo
        self._details = detail_repo
        self._auth_service = auth_service

    # -- internal builders (no permission check: the checks and the guard use them) ------------------------
    def bills_and_payments(self, customer_id: str):
        sales = [
            s for s in self._sales.list_by_customer(customer_id)
            if s.payment_method == PaymentMethod.CREDIT.value and s.status == SaleStatus.COMPLETED.value
        ]
        details = self._details.map_for_sales([s.id for s in sales])
        raw = []
        for s in sales:
            d = details.get(s.id)
            raw.append((local_date_of(s.sale_at), s.sale_at.timestamp(), LedgerBill(
                kind="sale", ref=s.receipt_number, bill_date=local_date_of(s.sale_at), amount=s.amount,
                vehicle_no=s.vehicle_number or (d.vehicle_no if d else None), slip_no=d.slip_no if d else None, sale_id=s.id, shift_id=s.shift_id,
            )))
        for b in self._bowser.bills_for_customer(customer_id):
            raw.append((b.bill_date, b.created_at.timestamp(), LedgerBill(
                kind="bowser", ref=b.bill_no, bill_date=b.bill_date, amount=b.total, vehicle_no=b.vehicle_no,
                slip_no=b.slip_no, shift_id=b.shift_id,
            )))
        bills = []
        for i, (_, _, bill) in enumerate(sorted(raw, key=lambda r: (r[0], r[1]))):
            bill.order = i
            bills.append(bill)
        pays = [
            LedgerPayment(p.payment_date, p.amount, p.payment_method, p.reference)
            for p in self._payments.list_for_customer(customer_id)
        ]
        return bills, pays

    def view(self, customer_id: str, as_of: Optional[date] = None) -> CustomerView:
        as_of = as_of or date.today()
        customer = self._customers.get_by_id(customer_id)
        if customer is None:
            raise NotFoundError(f"Customer not found: {customer_id}")
        account = self._accounts.get_by_customer_id(customer_id)
        bills, pays = self.bills_and_payments(customer_id)
        summary = apply_payments(bills, pays, as_of)
        limit = account.credit_limit if account else None
        overdue_days = 0
        if account and summary.oldest_unpaid is not None:
            overdue_days = max(0, summary.oldest_unpaid.age_days - account.payment_due_days)
        return CustomerView(
            customer_id=customer.id, name=customer.name, phone=customer.phone, credit_limit=limit,
            payment_due_days=account.payment_due_days if account else None, summary=summary, payments=pays,
            available=(limit - summary.balance) if limit is not None else None,
            overdue=overdue_days > 0, overdue_days=overdue_days, as_of=as_of,
        )

    def chase_accounts(self):
        """Credit accounts the owners follow up (everything except the internal bowser account)."""
        return [a for a in self._accounts.list_all() if not (a.customer and a.customer.name == BOWSER_CUSTOMER_NAME)]

    # -- permissioned reads -----------------------------------------------------------------------------------
    @require_permission(Permission.CREDIT_VIEW.value)
    def customer_ledger(self, actor_user_id: str, customer_id: str, as_of: Optional[date] = None) -> CustomerView:
        return self.view(customer_id, as_of)

    @require_permission(Permission.CREDIT_VIEW.value)
    def ageing(self, actor_user_id: str, as_of: Optional[date] = None) -> AgeingReport:
        as_of = as_of or date.today()
        rows: List[AgeingRow] = []
        totals = {name: _Z for name in BUCKETS}
        for acct in self.chase_accounts():
            v = self.view(acct.customer_id, as_of)
            if v.summary.balance == 0 and not v.summary.bills:
                continue
            old = v.summary.oldest_unpaid
            rows.append(AgeingRow(
                customer_id=v.customer_id, name=v.name, balance=v.summary.balance, buckets=dict(v.summary.buckets),
                oldest_unpaid_ref=old.ref if old else None, oldest_unpaid_date=old.bill_date if old else None,
                oldest_unpaid_age=old.age_days if old else None, credit_limit=v.credit_limit,
                over_limit=v.credit_limit is not None and v.summary.balance > v.credit_limit, overdue=v.overdue,
            ))
            for name in BUCKETS:
                totals[name] += v.summary.buckets[name]
        rows.sort(key=lambda r: (-(r.oldest_unpaid_age or -1), r.name))
        return AgeingReport(as_of=as_of, rows=rows, totals=totals, total_balance=sum((r.balance for r in rows), _Z))

    @require_permission(Permission.CREDIT_VIEW.value)
    def statement(self, actor_user_id: str, customer_id: str, date_from: date, date_to: date) -> StatementView:
        if date_to < date_from:
            raise ValueError("The end date cannot be before the start date")
        customer = self._customers.get_by_id(customer_id)
        if customer is None:
            raise NotFoundError(f"Customer not found: {customer_id}")
        bills, pays = self.bills_and_payments(customer_id)
        opening, lines, closing = statement_lines(bills, pays, date_from, date_to)
        in_range_bills = [b for b in bills if b.bill_date <= date_to]
        apply_payments(in_range_bills, [p for p in pays if p.pay_date <= date_to], date_to)
        return StatementView(
            customer_id=customer.id, name=customer.name, date_from=date_from, date_to=date_to,
            opening_balance=opening, lines=lines, closing_balance=closing,
            bills=[b for b in in_range_bills if b.bill_date >= date_from or b.outstanding > 0],
        )

"""Credit control: a customer's history, ageing, the limit check, recovery follow-ups, approvals and statements.

Thin: every figure comes from CustomerLedgerService / CreditControlService (app/services). The existing
/credit/accounts routes are untouched and keep working.
"""

from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Response

from api import reporting
from api.deps import CurrentUser, current_user, get_services
from api.schemas import In, MoneyIn, MoneyOut, OptionalReason, Out
from api.services import Services
from app.services.customer_ledger import BUCKETS
from app.services.report_service import TableReport

router = APIRouter(tags=["credit-control"])


class LedgerBillOut(Out):
    kind: str
    ref: str
    bill_date: date
    amount: MoneyOut
    paid: MoneyOut
    outstanding: MoneyOut
    age_days: int
    days_to_pay: Optional[int] = None
    vehicle_no: Optional[str] = None
    slip_no: Optional[str] = None
    sale_id: Optional[str] = None


class PaymentRowOut(Out):
    pay_date: date
    amount: MoneyOut
    method: str
    reference: Optional[str] = None


class FollowUpOut(Out):
    id: str
    customer_id: str
    followed_on: date
    by: Optional[str] = None
    method: str
    note: Optional[str] = None
    promised_date: Optional[date] = None
    promised_amount: Optional[MoneyOut] = None
    status: str


class OverrideRowOut(Out):
    created_at: str
    amount: MoneyOut
    outstanding_before: MoneyOut
    credit_limit: MoneyOut
    reason: str
    approved_by: str


class CustomerDetailOut(Out):
    customer_id: str
    name: str
    phone: Optional[str] = None
    credit_limit: Optional[MoneyOut] = None
    payment_due_days: Optional[int] = None
    balance: MoneyOut
    available: Optional[MoneyOut] = None
    total_billed: MoneyOut
    total_paid: MoneyOut
    unapplied: MoneyOut
    largest_outstanding_ever: MoneyOut
    average_days_to_pay: Optional[str] = None
    overdue: bool
    overdue_days: int
    buckets: dict[str, MoneyOut]
    oldest_unpaid: Optional[LedgerBillOut] = None
    approval: str
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    bills: list[LedgerBillOut]
    payments: list[PaymentRowOut]
    follow_ups: list[FollowUpOut]
    overrides: list[OverrideRowOut]


class CustomerRowOut(Out):
    customer_id: str
    name: str
    credit_limit: Optional[MoneyOut] = None
    balance: MoneyOut
    available: Optional[MoneyOut] = None
    overdue: bool
    overdue_days: int
    oldest_unpaid_age: Optional[int] = None
    approval: str


class AgeingRowOut(Out):
    customer_id: str
    name: str
    balance: MoneyOut
    buckets: dict[str, MoneyOut]
    oldest_unpaid_ref: Optional[str] = None
    oldest_unpaid_date: Optional[date] = None
    oldest_unpaid_age: Optional[int] = None
    credit_limit: Optional[MoneyOut] = None
    over_limit: bool
    overdue: bool


class AgeingOut(Out):
    as_of: date
    bucket_names: list[str]
    rows: list[AgeingRowOut]
    totals: dict[str, MoneyOut]
    total_balance: MoneyOut


class LimitCheckOut(Out):
    customer_id: str
    customer_name: str
    outstanding: MoneyOut
    credit_limit: Optional[MoneyOut] = None
    this_bill: MoneyOut
    would_become: MoneyOut
    available: Optional[MoneyOut] = None
    over_limit: bool
    mode: str
    approval: str
    problem: Optional[str] = None


class ApproverOut(Out):
    id: str
    name: str


class DueOut(Out):
    customer_id: str
    name: str
    reason: str
    detail: str
    promised_date: Optional[date] = None
    promised_amount: Optional[MoneyOut] = None
    balance: MoneyOut
    follow_up_id: Optional[str] = None


class FollowUpIn(In):
    method: Literal["call", "visit", "message", "other"]
    note: Optional[str] = None
    followed_on: Optional[date] = None
    promised_date: Optional[date] = None
    promised_amount: Optional[MoneyIn] = None


class CloseFollowUpIn(In):
    outcome: Literal["kept", "broken", "cancelled"]


class DecideIn(In):
    approve: bool
    note: OptionalReason


class BillDetailsIn(In):
    vehicle_no: Optional[str] = None
    slip_no: Optional[str] = None


class CreditDoneOut(Out):
    id: str


class CustomerStatementOut(Out):
    customer_id: str
    name: str
    date_from: date
    date_to: date
    opening_balance: MoneyOut
    closing_balance: MoneyOut
    lines: list[dict]
    bills: list[LedgerBillOut]
    report: reporting.ReportView


def _bill(b) -> LedgerBillOut:
    return LedgerBillOut(
        kind=b.kind, ref=b.ref, bill_date=b.bill_date, amount=b.amount, paid=b.paid, outstanding=b.outstanding,
        age_days=b.age_days, days_to_pay=b.days_to_pay, vehicle_no=b.vehicle_no, slip_no=b.slip_no, sale_id=b.sale_id,
    )


def _follow(services: Services, f) -> FollowUpOut:
    return FollowUpOut(
        id=f.id, customer_id=f.customer_id, followed_on=f.followed_on, by=f.by_user.username if f.by_user else None,
        method=f.method, note=f.note, promised_date=f.promised_date, promised_amount=f.promised_amount, status=f.status,
    )


@router.get("/credit/customers", response_model=list[CustomerRowOut])
def customers(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    services.credit_ledger.chase_accounts  # noqa: B018  (permission is checked per view below)
    out = []
    for a in services.credit_ledger.chase_accounts():
        v = services.credit_ledger.customer_ledger(user.id, a.customer_id)
        old = v.summary.oldest_unpaid
        out.append(CustomerRowOut(
            customer_id=v.customer_id, name=v.name, credit_limit=v.credit_limit, balance=v.summary.balance,
            available=v.available, overdue=v.overdue, overdue_days=v.overdue_days,
            oldest_unpaid_age=old.age_days if old else None, approval=services.credit_control.approval_status(a.customer_id),
        ))
    return sorted(out, key=lambda r: r.name)


@router.get("/credit/customers/{customer_id}", response_model=CustomerDetailOut)
def customer_detail(customer_id: str, as_of: Optional[date] = None, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    v = services.credit_ledger.customer_ledger(user.id, customer_id, as_of)
    s = v.summary
    row = services.credit_control.approval_row(customer_id)
    overrides = [o for o in services.credit_control.list_overrides(user.id) if o.customer_id == customer_id]
    return CustomerDetailOut(
        customer_id=v.customer_id, name=v.name, phone=v.phone, credit_limit=v.credit_limit,
        payment_due_days=v.payment_due_days, balance=s.balance, available=v.available, total_billed=s.total_billed,
        total_paid=s.total_paid, unapplied=s.unapplied, largest_outstanding_ever=s.largest_outstanding_ever,
        average_days_to_pay=str(s.average_days_to_pay) if s.average_days_to_pay is not None else None,
        overdue=v.overdue, overdue_days=v.overdue_days, buckets=s.buckets,
        oldest_unpaid=_bill(s.oldest_unpaid) if s.oldest_unpaid else None,
        approval=services.credit_control.approval_status(customer_id),
        approved_by=row.decided_by.username if row and row.decided_by else None,
        approved_at=row.decided_at.isoformat() if row and row.decided_at else None,
        bills=[_bill(b) for b in sorted(s.bills, key=lambda b: (b.bill_date, b.order), reverse=True)],
        payments=[PaymentRowOut(pay_date=p.pay_date, amount=p.amount, method=p.method, reference=p.reference) for p in sorted(v.payments, key=lambda p: p.pay_date, reverse=True)],
        follow_ups=[_follow(services, f) for f in services.credit_control.follow_ups(user.id, customer_id)],
        overrides=[OverrideRowOut(created_at=o.created_at.isoformat(), amount=o.amount, outstanding_before=o.outstanding_before, credit_limit=o.credit_limit, reason=o.reason, approved_by=o.approved_by.username if o.approved_by else "") for o in overrides],
    )


@router.get("/credit/ageing", response_model=AgeingOut)
def ageing(as_of: Optional[date] = None, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    a = services.credit_ledger.ageing(user.id, as_of)
    return AgeingOut(
        as_of=a.as_of, bucket_names=list(BUCKETS), total_balance=a.total_balance, totals=a.totals,
        rows=[AgeingRowOut(
            customer_id=r.customer_id, name=r.name, balance=r.balance, buckets=r.buckets, oldest_unpaid_ref=r.oldest_unpaid_ref,
            oldest_unpaid_date=r.oldest_unpaid_date, oldest_unpaid_age=r.oldest_unpaid_age, credit_limit=r.credit_limit,
            over_limit=r.over_limit, overdue=r.overdue,
        ) for r in a.rows],
    )


@router.get("/credit/check", response_model=LimitCheckOut)
def check_limit(customer_id: str, amount: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    """Balance and limit while a credit bill is being typed: what the customer owes, and what this bill would make it."""
    services.credit_ledger.customer_ledger(user.id, customer_id)  # CREDIT_VIEW
    c = services.credit_control.check_sale(customer_id, Decimal(amount))
    return LimitCheckOut(
        customer_id=c.customer_id, customer_name=c.customer_name, outstanding=c.outstanding, credit_limit=c.credit_limit,
        this_bill=c.amount, would_become=c.projected, available=c.available, over_limit=c.over_limit, mode=c.mode,
        approval=c.approval, problem=c.problem,
    )


@router.get("/credit/approvers", response_model=list[ApproverOut])
def approvers(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [ApproverOut(id=u.id, name=f"{u.first_name or ''} {u.last_name or ''}".strip() or u.username) for u in services.credit_control.approvers(user.id)]


@router.get("/credit/chase", response_model=list[DueOut])
def chase(as_of: Optional[date] = None, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [DueOut.model_validate(i, from_attributes=True) for i in services.credit_control.due_to_chase(user.id, as_of)]


@router.post("/credit/customers/{customer_id}/follow-ups", response_model=FollowUpOut, status_code=201)
def add_follow_up(customer_id: str, body: FollowUpIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    f = services.credit_control.add_follow_up(user.id, customer_id, body.method, body.note, body.followed_on, body.promised_date, body.promised_amount)
    return _follow(services, f)


@router.post("/credit/follow-ups/{follow_up_id}/close", response_model=FollowUpOut)
def close_follow_up(follow_up_id: str, body: CloseFollowUpIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return _follow(services, services.credit_control.close_follow_up(user.id, follow_up_id, body.outcome))


@router.post("/credit/approvals/{customer_id}", response_model=CreditDoneOut)
def decide(customer_id: str, body: DecideIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    row = services.credit_control.decide_customer(user.id, customer_id, body.approve, body.note)
    return CreditDoneOut(id=row.id)


@router.put("/credit/bills/{sale_id}/details", response_model=CreditDoneOut)
def bill_details(sale_id: str, body: BillDetailsIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return CreditDoneOut(id=services.credit_control.set_bill_details(user.id, sale_id, body.vehicle_no, body.slip_no).id)


def _statement_table(view) -> TableReport:
    rows = [["", "Opening balance", "", "", "", "", f"{view.opening_balance:.2f}"]]
    for l in view.lines:
        rows.append([
            l.line_date.strftime("%Y-%m-%d"), l.document, l.vehicle_no or "", l.slip_no or "",
            f"{l.debit:.2f}" if l.debit else "", f"{l.credit:.2f}" if l.credit else "", f"{l.balance:.2f}",
        ])
    rows.append(["", "Closing balance", "", "", "", "", f"{view.closing_balance:.2f}"])
    rows.append(["", "", "", "", "", "", ""])
    rows.append(["Bill-wise", "Bill", "Vehicle", "Slip", "Amount", "Paid", "Outstanding (age in days)"])
    for b in view.bills:
        rows.append([
            b.bill_date.strftime("%Y-%m-%d"), ("Bowser bill " if b.kind == "bowser" else "Bill ") + b.ref, b.vehicle_no or "",
            b.slip_no or "", f"{b.amount:.2f}", f"{b.paid:.2f}", f"{b.outstanding:.2f} ({b.age_days} d)" if b.outstanding else "0.00",
        ])
    return TableReport(
        title=f"Statement - {view.name} - {view.date_from} to {view.date_to}",
        headers=["Date", "Document", "Vehicle", "Slip", "Debit", "Credit", "Balance"],
        rows=rows,
    )


@router.get("/credit/customers/{customer_id}/statement", response_model=CustomerStatementOut)
def customer_statement(customer_id: str, date_from: date, date_to: date, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    v = services.credit_ledger.statement(user.id, customer_id, date_from, date_to)
    return CustomerStatementOut(
        customer_id=v.customer_id, name=v.name, date_from=v.date_from, date_to=v.date_to, opening_balance=v.opening_balance,
        closing_balance=v.closing_balance,
        lines=[{"date": l.line_date.isoformat(), "document": l.document, "vehicle_no": l.vehicle_no, "slip_no": l.slip_no,
                "debit": str(l.debit), "credit": str(l.credit), "balance": str(l.balance)} for l in v.lines],
        bills=[_bill(b) for b in v.bills],
        report=reporting.view(_statement_table(v), services.settings.get_company_profile()),
    )


@router.get("/credit/customers/{customer_id}/statement.{kind}")
def customer_statement_file(
    customer_id: str, kind: Literal["pdf", "xlsx"], date_from: date, date_to: date,
    user: CurrentUser = Depends(current_user), services: Services = Depends(get_services),
) -> Response:
    v = services.credit_ledger.statement(user.id, customer_id, date_from, date_to)
    return reporting.file_response(_statement_table(v), kind)

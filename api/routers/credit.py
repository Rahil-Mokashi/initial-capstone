"""Credit accounts, customer payments and statements. Same CreditService calls as app/ui/credit_window.py."""

from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Response

from api import reporting
from api.deps import CurrentUser, current_user, get_services
from api.schemas import In, MoneyIn, MoneyOut, OptionalReason, Out
from api.services import Services
from app.core.constants import PaymentMethod
from app.schemas.credit import CreditAccountCreate, CustomerPaymentCreate
from app.services.report_service import TableReport

router = APIRouter(tags=["credit"])


class AccountOut(Out):
    customer_id: str
    customer: Optional[str] = None
    credit_limit: MoneyOut
    outstanding: MoneyOut
    overdue: bool
    payment_due_days: int


class StatementEntry(Out):
    entry_date: date
    description: str
    debit: Optional[MoneyOut] = None
    credit: Optional[MoneyOut] = None
    running_balance: MoneyOut


class StatementOut(Out):
    customer: Optional[str] = None
    entries: list[StatementEntry]
    running_balance: MoneyOut
    report: reporting.ReportView


class AccountIn(In):
    customer_id: str
    credit_limit: MoneyIn
    payment_due_days: int = 30


class LimitIn(In):
    new_limit: MoneyIn
    reason: OptionalReason


class CustomerPaymentIn(In):
    customer_id: str
    amount: MoneyIn
    payment_method: PaymentMethod
    reference: Optional[str] = None
    remarks: Optional[str] = None


class CustomerPaymentOut(Out):
    id: str
    amount: MoneyOut


def _account(services: Services, user_id: str, a) -> AccountOut:
    return AccountOut(
        customer_id=a.customer_id,
        customer=a.customer.name if a.customer else None,
        credit_limit=a.credit_limit,
        outstanding=services.credit.get_outstanding_balance(user_id, a.customer_id),
        overdue=services.credit.is_overdue(user_id, a.customer_id),
        payment_due_days=a.payment_due_days,
    )


def _statement_report(customer_name: str, entries) -> TableReport:
    """The same table Qt's statement dialog prints and exports (built there in the dialog)."""
    rows = [
        [e.entry_date.strftime("%Y-%m-%d"), e.description, f"{e.debit:.2f}" if e.debit else "", f"{e.credit:.2f}" if e.credit else ""]
        for e in entries
    ]
    running = entries[-1].running_balance if entries else Decimal("0")
    rows.append(["", "Running Balance", "", f"{running:.2f}"])
    title = f"Customer Statement - {customer_name}" if customer_name else "Customer Statement"
    return TableReport(title=title, headers=["Date", "Description", "Debit", "Credit"], rows=rows)


def _name(services: Services, user_id: str, customer_id: str) -> str:
    for a in services.credit.list_credit_accounts(user_id):
        if a.customer_id == customer_id and a.customer:
            return a.customer.name
    return ""


@router.get("/credit/accounts", response_model=list[AccountOut])
def list_accounts(user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return [_account(services, user.id, a) for a in services.credit.list_credit_accounts(user.id)]


@router.post("/credit/accounts", response_model=AccountOut, status_code=201)
def open_account(body: AccountIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    a = services.credit.create_credit_account(user.id, CreditAccountCreate(**body.model_dump()))
    return _account(services, user.id, a)


@router.post("/credit/accounts/{customer_id}/limit", response_model=AccountOut)
def change_limit(customer_id: str, body: LimitIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    a = services.credit.set_credit_limit(user.id, customer_id, Decimal(body.new_limit), body.reason)
    return _account(services, user.id, a)


@router.post("/credit/payments", response_model=CustomerPaymentOut, status_code=201)
def record_payment(body: CustomerPaymentIn, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    return services.credit.record_customer_payment(user.id, CustomerPaymentCreate(**body.model_dump()))


@router.get("/credit/accounts/{customer_id}/statement", response_model=StatementOut)
def statement(customer_id: str, user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)):
    entries = services.credit.get_customer_statement(user.id, customer_id)
    name = _name(services, user.id, customer_id)
    return StatementOut(
        customer=name or None,
        entries=[
            StatementEntry(
                entry_date=e.entry_date, description=e.description, debit=e.debit or None, credit=e.credit or None, running_balance=e.running_balance
            )
            for e in entries
        ],
        running_balance=entries[-1].running_balance if entries else Decimal("0"),
        report=reporting.view(_statement_report(name, entries)),
    )


@router.get("/credit/accounts/{customer_id}/statement.{kind}")
def statement_file(
    customer_id: str, kind: Literal["pdf", "xlsx"], user: CurrentUser = Depends(current_user), services: Services = Depends(get_services)
) -> Response:
    entries = services.credit.get_customer_statement(user.id, customer_id)
    report = _statement_report(_name(services, user.id, customer_id), entries)
    return reporting.file_response(report, kind)

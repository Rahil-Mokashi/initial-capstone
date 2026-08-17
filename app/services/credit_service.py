"""Credit customer management (problemstatement.md #18, Phase 13).

A credit sale is a Sale (Phase 11) with payment_method=CREDIT - there is
no separate CreditSale table, per the design note recorded in
ROADMAP.md when this phase was scoped. Outstanding balance is always
recomputed from Sale/CustomerPayment data, never stored/incremented,
matching the "recompute from scratch, never let it drift" approach
already used for SupplierInvoice.status and PurchaseOrder.status.

ensure_credit_available is deliberately undecorated (no
@require_permission): it exists only to be called by SaleService as
part of an action the acting attendant is already authorized to
perform (SALE_MANAGE), the same reasoning behind TankService's
*_as_related_action split - a credit-limit check is not itself a
"view credit accounts" action that should require CREDIT_VIEW.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional

from app.core.constants import PaymentMethod, Permission, SaleStatus
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_permission
from app.repositories.base import session_for, unit_of_work
from app.models.credit_account import CreditAccount
from app.models.customer_payment import CustomerPayment
from app.schemas.credit import CreditAccountCreate, CustomerPaymentCreate


@dataclass
class CustomerStatementEntry:
    entry_date: date
    description: str
    debit: Decimal
    credit: Decimal
    running_balance: Decimal


class CreditService:
    def __init__(self, credit_account_repo, customer_payment_repo, customer_repo, sale_repo, audit_repo, auth_service):
        self._credit_account_repo = credit_account_repo
        self._customer_payment_repo = customer_payment_repo
        self._customer_repo = customer_repo
        self._sale_repo = sale_repo
        self._audit_repo = audit_repo
        self._auth_service = auth_service
        self._session = session_for(credit_account_repo)

    @require_permission(Permission.CREDIT_MANAGE.value)
    def create_credit_account(self, actor_user_id: str, data: CreditAccountCreate) -> CreditAccount:
        customer = self._customer_repo.get_by_id(data.customer_id)
        if not customer:
            raise NotFoundError(f"Customer not found: {data.customer_id}")
        if self._credit_account_repo.get_by_customer_id(data.customer_id):
            raise ConflictError(f"{customer.name} already has a credit account")

        account = CreditAccount(
            customer_id=data.customer_id,
            credit_limit=data.credit_limit,
            payment_due_days=data.payment_due_days,
            created_by_id=actor_user_id,
        )
        account = self._credit_account_repo.add(account)
        self._audit_repo.record(
            event_type="credit_account_created",
            actor_id=actor_user_id,
            entity_type="CreditAccount",
            entity_id=account.id,
            description=f"Opened credit account for {customer.name} with limit {data.credit_limit}",
        )
        return account

    @require_permission(Permission.CREDIT_MANAGE.value)
    def set_credit_limit(self, actor_user_id: str, customer_id: str, new_limit: Decimal, reason: str) -> CreditAccount:
        if not reason or not reason.strip():
            raise ValueError("A reason is required to change a credit limit")
        if new_limit <= 0:
            raise ValueError("credit_limit must be greater than zero")

        account = self._get_account_or_raise(customer_id)
        old_limit = account.credit_limit
        account.credit_limit = new_limit
        account = self._credit_account_repo.update(account)

        self._audit_repo.record(
            event_type="credit_limit_changed",
            actor_id=actor_user_id,
            entity_type="CreditAccount",
            entity_id=account.id,
            description=reason.strip(),
            old_value=str(old_limit),
            new_value=str(new_limit),
        )
        return account

    @require_permission(Permission.CREDIT_VIEW.value)
    def get_credit_account(self, actor_user_id: str, customer_id: str) -> Optional[CreditAccount]:
        return self._credit_account_repo.get_by_customer_id(customer_id)

    @require_permission(Permission.CREDIT_VIEW.value)
    def list_credit_accounts(self, actor_user_id: str) -> List[CreditAccount]:
        return self._credit_account_repo.list_all()

    @require_permission(Permission.CREDIT_MANAGE.value)
    def record_customer_payment(self, actor_user_id: str, data: CustomerPaymentCreate) -> CustomerPayment:
        """Money received against a credit account. The payment row and its audit record commit together or not at all."""
        with unit_of_work(self._session):
            return self._record_customer_payment_impl(actor_user_id, data)

    def _record_customer_payment_impl(self, actor_user_id: str, data: CustomerPaymentCreate):
        if not self._credit_account_repo.get_by_customer_id(data.customer_id):
            raise NotFoundError("This customer has no credit account")

        payment = CustomerPayment(
            customer_id=data.customer_id,
            amount=data.amount,
            payment_date=date.today(),
            payment_method=data.payment_method.value,
            reference=data.reference,
            recorded_by_id=actor_user_id,
            remarks=data.remarks,
        )
        payment = self._customer_payment_repo.add(payment)

        self._audit_repo.record(
            event_type="customer_payment_recorded",
            actor_id=actor_user_id,
            entity_type="CustomerPayment",
            entity_id=payment.id,
            description=f"Received {data.amount} from customer via {data.payment_method.value}",
        )
        return payment

    @require_permission(Permission.CREDIT_VIEW.value)
    def get_outstanding_balance(self, actor_user_id: str, customer_id: str) -> Decimal:
        return self._compute_outstanding_balance(customer_id)

    @require_permission(Permission.CREDIT_VIEW.value)
    def is_overdue(self, actor_user_id: str, customer_id: str) -> bool:
        return self._is_overdue(customer_id)

    @require_permission(Permission.CREDIT_VIEW.value)
    def get_customer_statement(self, actor_user_id: str, customer_id: str) -> List[CustomerStatementEntry]:
        credit_sales = [
            sale
            for sale in self._sale_repo.list_by_customer(customer_id)
            if sale.payment_method == PaymentMethod.CREDIT.value and sale.status == SaleStatus.COMPLETED.value
        ]
        payments = self._customer_payment_repo.list_for_customer(customer_id)

        events = [(sale.sale_at.date(), f"Sale {sale.receipt_number}", sale.amount, Decimal("0")) for sale in credit_sales]
        events += [(payment.payment_date, "Payment received", Decimal("0"), payment.amount) for payment in payments]
        events.sort(key=lambda item: item[0])

        entries = []
        running_balance = Decimal("0")
        for entry_date, description, debit, credit in events:
            running_balance += debit - credit
            entries.append(CustomerStatementEntry(entry_date, description, debit, credit, running_balance))
        return entries

    def ensure_credit_available(self, customer_id: str, additional_amount: Decimal) -> None:
        account = self._credit_account_repo.get_by_customer_id(customer_id)
        if not account:
            raise ConflictError("This customer has no credit account - open one before recording a credit sale")

        outstanding = self._compute_outstanding_balance(customer_id)
        if outstanding + additional_amount > account.credit_limit:
            raise ConflictError(
                f"This sale would bring the outstanding balance to {outstanding + additional_amount}, "
                f"exceeding the credit limit of {account.credit_limit}"
            )

    def _compute_outstanding_balance(self, customer_id: str) -> Decimal:
        credit_sales_total = sum(
            (
                sale.amount
                for sale in self._sale_repo.list_by_customer(customer_id)
                if sale.payment_method == PaymentMethod.CREDIT.value and sale.status == SaleStatus.COMPLETED.value
            ),
            Decimal("0"),
        )
        payments_total = sum((p.amount for p in self._customer_payment_repo.list_for_customer(customer_id)), Decimal("0"))
        return credit_sales_total - payments_total

    def _is_overdue(self, customer_id: str) -> bool:
        account = self._credit_account_repo.get_by_customer_id(customer_id)
        if not account or self._compute_outstanding_balance(customer_id) <= 0:
            return False

        credit_sales = [
            sale
            for sale in self._sale_repo.list_by_customer(customer_id)
            if sale.payment_method == PaymentMethod.CREDIT.value and sale.status == SaleStatus.COMPLETED.value
        ]
        if not credit_sales:
            return False

        oldest_sale = min(credit_sales, key=lambda sale: sale.sale_at)
        due_by = oldest_sale.sale_at.date() + timedelta(days=account.payment_due_days)
        return date.today() > due_by

    def _get_account_or_raise(self, customer_id: str) -> CreditAccount:
        account = self._credit_account_repo.get_by_customer_id(customer_id)
        if not account:
            raise NotFoundError("This customer has no credit account")
        return account

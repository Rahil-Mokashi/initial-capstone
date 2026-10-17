"""A credit customer made at the Terminal counter (Owner Choice W-34).

The data-entry person types a name (and phone) while billing. The same person is never made twice: a phone number
(last ten digits) is matched first, then the name. A new one gets a credit limit of 0 and an approval row saying "new, owner to
approve". Their first credit bill goes through (CreditControlService.authorize_sale); the next waits for an owner.
"""

from decimal import Decimal
from typing import Optional, Tuple

from app.core.constants import Permission
from app.core.permissions import require_permission
from app.database.base import StatusEnum
from app.models.credit_account import CreditAccount
from app.models.credit_recovery import CustomerApproval
from app.models.customer import Customer
from app.repositories.base import session_for, unit_of_work

DEFAULT_DUE_DAYS = 30  # ponytail: a fixed 30 days until the owners say otherwise; the owner can change it on the account


def _digits(phone: Optional[str]) -> str:
    return "".join(c for c in (phone or "") if c.isdigit())[-10:]


def _name_key(name: Optional[str]) -> str:
    return " ".join((name or "").split()).casefold()


class CounterCustomerService:
    def __init__(self, customer_repo, account_repo, approval_repo, audit_repo, auth_service, settings):
        self._customers = customer_repo
        self._accounts = account_repo
        self._approvals = approval_repo
        self._audit_repo = audit_repo
        self._auth_service = auth_service
        self._settings = settings
        self._session = session_for(customer_repo)

    def match(self, name: str, phone: Optional[str]) -> Optional[Customer]:
        everyone = self._customers.list_all()
        digits = _digits(phone)
        if len(digits) >= 7:
            for c in everyone:
                if _digits(c.phone) == digits:
                    return c
        key = _name_key(name)
        return next((c for c in everyone if _name_key(c.name) == key), None) if key else None

    @require_permission(Permission.SALE_MANAGE.value)
    def find_or_create(self, actor_user_id: str, name: str, phone: Optional[str] = None) -> Tuple[Customer, bool]:
        """(customer, matched). matched=True means an existing person was found and nothing new was made."""
        name = " ".join((name or "").split())
        if not name:
            raise ValueError("Enter the customer's name.")
        with unit_of_work(self._session):
            found = self.match(name, phone)
            customer = found or self._customers.add(Customer(name=name, phone=(phone or "").strip() or None, status=StatusEnum.ACTIVE.value))
            if found is None:
                self._audit_repo.record(
                    event_type="customer_created", actor_id=actor_user_id, entity_type="Customer", entity_id=customer.id,
                    description=f"Created customer {name} at the counter",
                )
            if self._settings.get("counter_customer_approval") == "on" and self._accounts.get_by_customer_id(customer.id) is None:
                account = self._accounts.add(CreditAccount(
                    customer_id=customer.id, credit_limit=Decimal("0.00"), payment_due_days=DEFAULT_DUE_DAYS, created_by_id=actor_user_id,
                ))
                row = self._approvals.add(CustomerApproval(
                    customer_id=customer.id, status="pending", requested_by_id=actor_user_id, counter_created=True,
                    note="New customer made at the counter: owner to approve and set a limit",
                ))
                self._audit_repo.record(
                    event_type="credit_customer_approval_requested", actor_id=actor_user_id, entity_type="CustomerApproval", entity_id=row.id,
                    description=f"{name}: credit account opened at the counter with a limit of 0; waiting for an owner (account {account.id})",
                )
            return customer, found is not None

"""Credit control: approving new credit customers, the limit check at the moment of sale (with an owner
override that is always recorded), and the recovery (chasing) log.

It sits BESIDE the existing CreditService and keeps its rules: the same permissions, the same audit log,
and CreditService's own limit check still runs underneath. The only addition to CreditService is a
one-shot `limit_override` context, used here and nowhere else.

Setting `credit_over_limit` (V-14): "warn" (default) lets an owner allow a sale past the limit, "block"
refuses it. Either way nothing happens silently: a refusal says why, an override is stored with who
allowed it and why, and the audit log gets an entry.
"""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

from app.core.constants import Permission
from app.core.vehicle import normalise_vehicle
from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.money import money
from app.core.permissions import require_permission
from app.models.credit_recovery import CreditBillDetail, CreditFollowUp, CreditLimitOverride, CustomerApproval
from app.repositories.base import session_for, unit_of_work

_Z = Decimal("0")
METHODS = ("call", "visit", "message", "other")


class CreditLimitExceeded(ConflictError):
    """Raised when a credit sale would pass the customer's limit and needs an owner's override."""

    def __init__(self, message: str, details: dict):
        super().__init__(message)
        self.details = details


@dataclass
class LimitCheck:
    customer_id: str
    customer_name: str
    outstanding: Decimal
    credit_limit: Optional[Decimal]
    amount: Decimal
    projected: Decimal
    available: Optional[Decimal]
    over_limit: bool
    mode: str  # "warn" | "block"
    approval: str  # "approved" | "pending" | "rejected" | "not_required"
    problem: Optional[str]  # why the sale cannot go ahead at all, if so


@dataclass
class Override:
    approver_id: str
    credential: str
    use_pin: bool
    reason: str


@dataclass
class DueItem:
    customer_id: str
    name: str
    reason: str  # "promise" | "overdue"
    detail: str
    promised_date: Optional[date]
    promised_amount: Optional[Decimal]
    balance: Decimal
    follow_up_id: Optional[str]


class CreditControlService:
    def __init__(self, ledger, account_repo, approval_repo, override_repo, follow_repo, detail_repo, sale_repo, settings,
                 user_repo, auth_service, audit_repo, credit_service):
        self._ledger = ledger
        self._accounts = account_repo
        self._approvals = approval_repo
        self._overrides = override_repo
        self._follow = follow_repo
        self._details = detail_repo
        self._sales = sale_repo
        self._settings = settings
        self._users = user_repo
        self._auth_service = auth_service
        self._audit_repo = audit_repo
        self._credit = credit_service
        self._session = session_for(approval_repo)

    # -- approval of new credit customers (V-10) ----------------------------------------------------------------
    def on_account_created(self, actor_user_id: str, customer_id: str) -> CustomerApproval:
        """Called right after a credit account is opened. Rule off: recorded as approved by whoever opened it."""
        existing = self._approvals.get_for_customer(customer_id)
        if existing is not None:
            return existing
        needs = self._settings.get("new_customer_approval") == "on"
        now = datetime.now(timezone.utc)
        row = self._approvals.add(CustomerApproval(
            customer_id=customer_id, status="pending" if needs else "approved", requested_by_id=actor_user_id,
            decided_by_id=None if needs else actor_user_id, decided_at=None if needs else now,
            note=None if needs else "Approval rule was off when the account was opened",
        ))
        self._audit_repo.record(
            event_type="credit_customer_approval_requested" if needs else "credit_customer_recorded",
            actor_id=actor_user_id, entity_type="CustomerApproval", entity_id=row.id,
            description=("Waiting for an owner to approve credit" if needs else "Credit account opened; approval rule off"),
        )
        return row

    def approval_status(self, customer_id: str) -> str:
        if self._settings.get("new_customer_approval") != "on":
            return "not_required"
        row = self._approvals.get_for_customer(customer_id)
        return row.status if row is not None else "approved"  # accounts that predate the rule are grandfathered

    def approval_row(self, customer_id: str) -> Optional[CustomerApproval]:
        return self._approvals.get_for_customer(customer_id)

    @require_permission(Permission.CREDIT_APPROVE.value)
    def decide_customer(self, actor_user_id: str, customer_id: str, approve: bool, note: str = "") -> CustomerApproval:
        with unit_of_work(self._session):
            row = self._approvals.get_for_customer(customer_id)
            if row is None:
                if self._accounts.get_by_customer_id(customer_id) is None:
                    raise NotFoundError("This customer has no credit account")
                row = self._approvals.add(CustomerApproval(customer_id=customer_id, status="pending", requested_by_id=actor_user_id))
            row.status = "approved" if approve else "rejected"
            row.decided_by_id, row.decided_at, row.note = actor_user_id, datetime.now(timezone.utc), (note or "").strip() or None
            self._approvals.save(row)
            self._audit_repo.record(
                event_type="credit_customer_approved" if approve else "credit_customer_rejected", actor_id=actor_user_id,
                entity_type="CustomerApproval", entity_id=row.id, description=f"{'Approved' if approve else 'Rejected'} credit for customer {customer_id}. {row.note or ''}".strip(),
            )
            return row

    @require_permission(Permission.CREDIT_VIEW.value)
    def pending_approvals(self, actor_user_id: str) -> List[CustomerApproval]:
        return [r for r in self._approvals.list_all() if r.status == "pending"]

    # -- the limit at the moment of sale (V-14) ----------------------------------------------------------------------
    def check_sale(self, customer_id: str, amount: Decimal) -> LimitCheck:
        """Everything the person entering a credit bill should see: balance, limit, what it would become."""
        v = self._ledger.view(customer_id)
        amount = money(amount)
        account = self._accounts.get_by_customer_id(customer_id)
        mode = self._settings.get("credit_over_limit")
        approval = self.approval_status(customer_id)
        outstanding = v.summary.balance
        projected = outstanding + amount
        limit = account.credit_limit if account else None
        over = limit is not None and projected > limit
        problem = None
        if account is None:
            problem = f"{v.name} has no credit account. Open one in Credit first."
        elif approval in ("pending", "rejected"):
            problem = (f"{v.name} is not approved for credit yet: an owner has to approve them first."
                       if approval == "pending" else f"{v.name} was not approved for credit.")
        return LimitCheck(
            customer_id=customer_id, customer_name=v.name, outstanding=outstanding, credit_limit=limit, amount=amount,
            projected=projected, available=(limit - outstanding) if limit is not None else None, over_limit=over,
            mode=mode, approval=approval, problem=problem,
        )

    def authorize_sale(self, actor_user_id: str, customer_id: str, amount: Decimal, override: Optional[Override]):
        """Returns None when the sale is fine as it stands, or the approved Override to use. Raises when it must stop."""
        chk = self.check_sale(customer_id, amount)
        details = {
            "customer": chk.customer_name, "outstanding": str(money(chk.outstanding)), "credit_limit": str(money(chk.credit_limit or _Z)),
            "this_bill": str(chk.amount), "would_become": str(money(chk.projected)), "mode": chk.mode,
        }
        if chk.problem:
            raise ConflictError(chk.problem)
        if not chk.over_limit:
            return None
        message = (f"{chk.customer_name} would owe {money(chk.projected)} with this bill, which is over the credit limit of "
                   f"{money(chk.credit_limit)} (now owing {money(chk.outstanding)}).")
        if chk.mode == "block":
            self._audit_repo.record(
                event_type="credit_sale_blocked", actor_id=actor_user_id, entity_type="Customer", entity_id=customer_id,
                description=message,
            )
            raise ConflictError(message + " Credit over the limit is switched to 'block' in settings.")
        if override is None:
            raise CreditLimitExceeded(message + " An owner can allow it.", {**details, "can_override": True})
        ok, error = self._auth_service.reauthenticate(override.approver_id, override.credential, use_pin=override.use_pin)
        if not ok:
            raise AuthenticationError(error or "The owner's password or PIN is not correct.")
        if not self._auth_service.check_permission(override.approver_id, Permission.CREDIT_OVERRIDE.value):
            self._auth_service.record_permission_denied(override.approver_id, Permission.CREDIT_OVERRIDE.value)
            raise PermissionDeniedError(Permission.CREDIT_OVERRIDE.value)
        return override

    def record_override(self, actor_user_id: str, sale, check_before: LimitCheck, override: Override) -> CreditLimitOverride:
        row = self._overrides.add(CreditLimitOverride(
            customer_id=check_before.customer_id, sale_id=sale.id, amount=sale.amount,
            outstanding_before=money(check_before.outstanding), credit_limit=check_before.credit_limit or _Z,
            reason=(override.reason or "").strip() or "No reason given", approved_by_id=override.approver_id,
            requested_by_id=actor_user_id,
        ))
        self._audit_repo.record(
            event_type="credit_limit_override", actor_id=override.approver_id, entity_type="Sale", entity_id=sale.id,
            description=f"Credit limit overridden for {check_before.customer_name}: bill {sale.receipt_number} for {sale.amount}, "
                        f"owing {money(check_before.outstanding)} against a limit of {money(check_before.credit_limit or _Z)}. "
                        f"Entered by {actor_user_id}. Reason: {row.reason}",
        )
        return row

    def override_sale_ids(self) -> set:
        return self._overrides.sale_ids()

    @require_permission(Permission.CREDIT_VIEW.value)
    def list_overrides(self, actor_user_id: str):
        return self._overrides.list_all()

    @require_permission(Permission.CREDIT_VIEW.value)
    def approvers(self, actor_user_id: str):
        """Active people who may allow a credit sale past the limit (for the 'ask an owner' box)."""
        return [u for u in self._users.list_all() if u.is_active and self._auth_service.check_permission(u.id, Permission.CREDIT_OVERRIDE.value)]

    # -- bill details (vehicle and slip numbers, J-05) --------------------------------------------------------------
    @require_permission(Permission.CREDIT_MANAGE.value)
    def set_bill_details(self, actor_user_id: str, sale_id: str, vehicle_no: Optional[str], slip_no: Optional[str]) -> CreditBillDetail:
        sale = self._sales.get_by_id(sale_id)
        if sale is None:
            raise NotFoundError(f"Sale not found: {sale_id}")
        with unit_of_work(self._session):
            row = self._details.get_for_sale(sale_id)
            vehicle, slip = normalise_vehicle(vehicle_no), (slip_no or "").strip() or None
            if sale.vehicle_number != vehicle:
                sale.vehicle_number = vehicle  # the sale's own column is the one the receipt and the daily report read
                self._sales.update(sale)
            if row is None:
                row = self._details.add(CreditBillDetail(sale_id=sale_id, vehicle_no=vehicle, slip_no=slip, updated_by_id=actor_user_id))
            else:
                row.vehicle_no, row.slip_no, row.updated_by_id = vehicle, slip, actor_user_id
                row.updated_at = datetime.now(timezone.utc)
                self._details.save(row)
            self._audit_repo.record(
                event_type="credit_bill_details_set", actor_id=actor_user_id, entity_type="Sale", entity_id=sale_id,
                description=f"Bill {sale.receipt_number}: vehicle {vehicle or '-'}, slip {slip or '-'}",
            )
            return row

    # -- recovery: the follow-up log and the chase list ------------------------------------------------------------------
    @require_permission(Permission.CREDIT_RECOVERY.value)
    def add_follow_up(
        self, actor_user_id: str, customer_id: str, method: str, note: Optional[str], followed_on: Optional[date] = None,
        promised_date: Optional[date] = None, promised_amount: Optional[Decimal] = None,
    ) -> CreditFollowUp:
        if method not in METHODS:
            raise ValueError(f"How did you contact them? Choose one of: {', '.join(METHODS)}")
        if promised_amount is not None and promised_amount <= 0:
            raise ValueError("A promised amount must be more than zero")
        if promised_amount is not None and promised_date is None:
            raise ValueError("Give the date they promised to pay")
        if self._accounts.get_by_customer_id(customer_id) is None:
            raise NotFoundError("This customer has no credit account")
        with unit_of_work(self._session):
            row = self._follow.add(CreditFollowUp(
                customer_id=customer_id, followed_on=followed_on or date.today(), by_user_id=actor_user_id, method=method,
                note=(note or "").strip() or None, promised_date=promised_date,
                promised_amount=money(promised_amount) if promised_amount is not None else None, status="open",
            ))
            self._audit_repo.record(
                event_type="credit_follow_up_recorded", actor_id=actor_user_id, entity_type="CreditFollowUp", entity_id=row.id,
                description=f"Followed up customer {customer_id} by {method}"
                + (f"; promised {row.promised_amount} by {promised_date}" if promised_date else ""),
            )
            return row

    @require_permission(Permission.CREDIT_RECOVERY.value)
    def close_follow_up(self, actor_user_id: str, follow_up_id: str, outcome: str) -> CreditFollowUp:
        if outcome not in ("kept", "broken", "cancelled"):
            raise ValueError("Outcome must be kept, broken or cancelled")
        with unit_of_work(self._session):
            row = self._follow.get(follow_up_id)
            if row is None:
                raise NotFoundError("Follow-up not found")
            if row.status != "open":
                raise ConflictError("This follow-up is already closed")
            row.status, row.closed_at, row.closed_by_id = outcome, datetime.now(timezone.utc), actor_user_id
            self._follow.save(row)
            self._audit_repo.record(
                event_type="credit_follow_up_closed", actor_id=actor_user_id, entity_type="CreditFollowUp", entity_id=row.id,
                description=f"Promise marked {outcome}",
            )
            return row

    @require_permission(Permission.CREDIT_VIEW.value)
    def follow_ups(self, actor_user_id: str, customer_id: str) -> List[CreditFollowUp]:
        return self._follow.list_for_customer(customer_id)

    @require_permission(Permission.CREDIT_VIEW.value)
    def due_to_chase(self, actor_user_id: str, as_of: Optional[date] = None) -> List[DueItem]:
        """Who to chase today: promises that have come due, then customers past their payment terms with no open promise."""
        as_of = as_of or date.today()
        items: List[DueItem] = []
        promised_customers = set()
        for f in self._follow.open_with_promise_on_or_before(as_of):
            v = self._ledger.view(f.customer_id, as_of)
            if v.summary.balance <= 0:
                continue  # already paid up: nothing to chase
            promised_customers.add(f.customer_id)
            late = (as_of - f.promised_date).days
            items.append(DueItem(
                f.customer_id, v.name, "promise",
                "Promised to pay today" if late == 0 else f"Promised to pay {late} day(s) ago",
                f.promised_date, f.promised_amount, v.summary.balance, f.id,
            ))
        last = self._follow.last_contact()
        for acct in self._ledger.chase_accounts():
            if acct.customer_id in promised_customers or self._follow.open_for_customer(acct.customer_id):
                continue
            v = self._ledger.view(acct.customer_id, as_of)
            if v.overdue and v.summary.balance > 0:
                seen = last.get(acct.customer_id)
                since = f", last contacted {(as_of - seen).days} day(s) ago" if seen else ", never contacted"
                items.append(DueItem(
                    acct.customer_id, v.name, "overdue", f"{v.overdue_days} day(s) past the payment terms{since}", None, None,
                    v.summary.balance, None,
                ))
        items.sort(key=lambda i: (0 if i.reason == "promise" else 1, -i.balance))
        return items

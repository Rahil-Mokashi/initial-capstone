"""Sales service layer (problemstatement.md #16, #17, Phases 11-12).

Depends on TankService (not just TankRepository) for the exact same
reason ProcurementService does: a sale moves fuel out of a tank through
the normal, audited ISSUE-transaction path, never a parallel one. rate
and amount are snapshotted from the fuel's current price at the moment
of sale (user-confirmed requirement, 2026-08-16: prices change over
time, so a completed sale's amount must never silently shift later).
Sales are never deleted - cancel_sale changes status and posts a
compensating ADJUSTMENT transaction to put the fuel back, matching the
project's VOID/REVERSE/ADJUST-not-DELETE rule.

Every sale also creates its own Payment record (problemstatement.md
#17: settlement is tracked separately from the sale itself, since fuel
can be dispensed - a completed sale - while money is still owed, e.g.
a CREDIT sale's payment starts PENDING). Payments live on this service
rather than a separate one because they're a 1:1 satellite of Sale,
created/reversed on the exact same permission (SALE_MANAGE) at the
exact same moments - the same reasoning already applied to folding
Customer CRUD in here rather than a standalone CustomerService.
"""

from decimal import Decimal
from typing import List, Optional

from app.core.constants import PaymentMethod, PaymentStatus, Permission, SaleStatus, ShiftStatus, TankTransactionType
from app.core.exceptions import ConflictError, NotFoundError
from app.core.money import money
from app.core.permissions import require_permission
from app.database.base import StatusEnum
from app.repositories.base import session_for, unit_of_work
from app.models.customer import Customer
from app.models.payment import Payment
from app.models.sale import Sale
from app.schemas.customer import CustomerCreate
from app.schemas.sale import SaleCreate
from app.schemas.tank import TankTransactionCreate
from app.services.fuel_service import FuelService


class SaleService:
    def __init__(self, sale_repo, shift_repo, nozzle_repo, fuel_repo, employee_repo, customer_repo, tank_repo, tank_service, audit_repo, auth_service, payment_repo, credit_service):
        self._sale_repo = sale_repo
        self._shift_repo = shift_repo
        self._nozzle_repo = nozzle_repo
        self._fuel_repo = fuel_repo
        self._employee_repo = employee_repo
        self._customer_repo = customer_repo
        self._tank_repo = tank_repo
        self._tank_service = tank_service
        self._audit_repo = audit_repo
        self._auth_service = auth_service
        self._payment_repo = payment_repo
        self._credit_service = credit_service
        self._session = session_for(sale_repo)

    @require_permission(Permission.SALE_MANAGE.value)
    def create_sale(self, actor_user_id: str, data: SaleCreate) -> Sale:
        """Record a sale, its tank issue and its payment as ONE transaction.

        This method writes to four tables (sales, tank_transactions,
        tanks, payments) and every one of those writes has to happen or
        none of them can. Without the unit of work each repository
        committed independently, so a failure partway through left fuel
        issued from a tank with no sale accounting for it, or a completed
        sale with no payment record — which then silently corrupted shift
        reconciliation. See CLAUDE.md: "Never allow partial financial
        writes."
        """
        return self._create_sale(actor_user_id, data)

    def create_sale_as_related_action(self, actor_user_id: str, data: SaleCreate) -> Sale:
        """Unchecked twin of create_sale, for a caller whose own permission
        check already authorizes this as a side effect of an action it's
        already doing - the same reasoning as
        TankService.record_transaction_as_related_action. Used by
        settle_assignment_cash below, on behalf of
        ShiftService.complete_nozzle_assignment (SHIFT_MANAGE), so
        completing an assignment doesn't also require the acting
        supervisor to separately hold SALE_MANAGE.
        """
        return self._create_sale(actor_user_id, data)

    def _create_sale(self, actor_user_id: str, data: SaleCreate) -> Sale:
        with unit_of_work(self._session):
            return self._create_sale_impl(actor_user_id, data)

    def settle_assignment_cash(self, actor_user_id: str, assignment) -> Optional[Sale]:
        """Auto-aggregate one nozzle assignment's cash sales into a single
        Sale when the assignment closes, so an attendant never manually
        enters a cash sale one at a time - only credit/UPI/card sales,
        where a customer link or a payment reference genuinely matters,
        still go through Terminal individually (user-requested design,
        2026-09-02: per-transaction cash entry doesn't scale to a busy
        forecourt on a single desktop terminal).

        Deliberately undecorated (no @require_permission), matching
        CreditService.ensure_credit_available's reasoning exactly: this
        exists only to be called by ShiftService.complete_nozzle_assignment
        as part of an action the acting supervisor is already authorized
        (SHIFT_MANAGE) to perform, not as a standalone "record a sale"
        action that should require its own SALE_MANAGE check.

        total dispensed, per the same opening/closing meter reading fuel
        reconciliation already trusts, minus whatever was already
        recorded individually during this assignment - by payment method,
        cash included, not just credit/UPI/card - is the remaining
        volume this settles. Cash has to be subtracted too, not just
        excluded: Terminal still lets anyone manually ring up an
        individual cash sale (e.g. a customer who wants a receipt), and
        skipping already-recorded cash here would double-count that
        volume into the aggregate on top of the individual sale already
        covering it. Returns None (and records nothing) if the remainder
        isn't positive - a zero or negative remainder means at least as
        much was already recorded as the meter says was dispensed at
        all, which is a discrepancy to investigate, not something to
        paper over with a fabricated sale (the sales table's own CHECK
        constraint would reject a non-positive quantity regardless).
        """
        if assignment.closing_meter is None:
            return None

        dispensed = assignment.closing_meter - assignment.opening_meter
        already_recorded = sum(
            (
                sale.quantity
                for sale in self._sale_repo.list_by_nozzle(assignment.nozzle_id)
                if sale.shift_id == assignment.shift_id
                and sale.employee_id == assignment.employee_id
                and sale.status == SaleStatus.COMPLETED.value
            ),
            Decimal("0"),
        )
        remaining_cash = dispensed - already_recorded
        if remaining_cash <= 0:
            return None

        data = SaleCreate(
            shift_id=assignment.shift_id,
            nozzle_id=assignment.nozzle_id,
            employee_id=assignment.employee_id,
            quantity=remaining_cash,
            payment_method=PaymentMethod.CASH,
            customer_id=None,
            remarks="Aggregate cash sale - auto-settled on nozzle assignment close",
        )
        return self.create_sale_as_related_action(actor_user_id, data)

    def _create_sale_impl(self, actor_user_id: str, data: SaleCreate) -> Sale:
        shift = self._shift_repo.get_by_id(data.shift_id)
        if not shift:
            raise NotFoundError(f"Shift not found: {data.shift_id}")
        if shift.status != ShiftStatus.OPEN.value:
            raise ConflictError("Cannot record a sale against a shift that is not open")

        nozzle = self._nozzle_repo.get_by_id(data.nozzle_id)
        if not nozzle:
            raise NotFoundError(f"Nozzle not found: {data.nozzle_id}")
        if nozzle.status != "active":
            raise ConflictError(f"Nozzle {nozzle.code} is not active")

        if not self._employee_repo.get_by_id(data.employee_id):
            raise NotFoundError(f"Employee not found: {data.employee_id}")

        if data.payment_method == PaymentMethod.CREDIT and not data.customer_id:
            raise ValueError("A customer is required for a credit sale")
        if data.customer_id and not self._customer_repo.get_by_id(data.customer_id):
            raise NotFoundError(f"Customer not found: {data.customer_id}")

        fuel = self._fuel_repo.get_by_id(nozzle.fuel_id)
        if not fuel:
            raise NotFoundError(f"Fuel type not found: {nozzle.fuel_id}")
        # Refuse to book a zero-value sale. Fuels are seeded at 0.00 and
        # stay there until a manager sets a real price, and a sale at
        # 0.00 looks completed and correct while silently understating
        # revenue everywhere downstream. See FuelService.
        FuelService.ensure_fuel_is_priced(fuel)

        tank_id = self._resolve_tank_id(nozzle)

        rate_per_liter = fuel.rate_per_liter
        # Settled to paise here, once, rather than left at whatever
        # precision quantity x rate happens to produce and rounded
        # implicitly (and with the wrong rounding mode) by the Numeric
        # column on the way in - see app/core/money.py.
        amount = money(data.quantity * rate_per_liter)

        if data.payment_method == PaymentMethod.CREDIT:
            self._credit_service.ensure_credit_available(data.customer_id, amount)

        receipt_number = self._sale_repo.next_receipt_number()
        sale = Sale(
            receipt_number=receipt_number,
            shift_id=data.shift_id,
            nozzle_id=data.nozzle_id,
            fuel_id=nozzle.fuel_id,
            employee_id=data.employee_id,
            quantity=data.quantity,
            rate_per_liter=rate_per_liter,
            amount=amount,
            payment_method=data.payment_method.value,
            customer_id=data.customer_id,
            status=SaleStatus.COMPLETED.value,
            recorded_by_id=actor_user_id,
            remarks=data.remarks,
        )
        sale = self._sale_repo.add(sale)

        transaction = self._tank_service.record_transaction_as_related_action(
            actor_user_id,
            tank_id,
            TankTransactionType.ISSUE,
            TankTransactionCreate(quantity=data.quantity, reference=receipt_number, remarks=f"Sale {receipt_number}"),
        )
        sale.tank_transaction_id = transaction.id
        sale = self._sale_repo.update(sale)

        payment_status = PaymentStatus.PENDING if data.payment_method == PaymentMethod.CREDIT else PaymentStatus.SUCCESS
        payment = Payment(
            sale_id=sale.id,
            amount=amount,
            method=data.payment_method.value,
            reference_number=data.reference_number,
            status=payment_status.value,
            shift_id=data.shift_id,
            attendant_id=data.employee_id,
            recorded_by_id=actor_user_id,
        )
        self._payment_repo.add(payment)

        self._audit_repo.record(
            event_type="sale_recorded",
            actor_id=actor_user_id,
            entity_type="Sale",
            entity_id=sale.id,
            description=f"Sold {data.quantity} of {fuel.fuel_type} for {amount} via {data.payment_method.value} ({receipt_number})",
        )
        return sale

    @require_permission(Permission.SALE_VIEW.value)
    def list_sales(self, actor_user_id: str, limit: Optional[int] = None, offset: int = 0) -> List[Sale]:
        """Newest first. limit defaults to None so reporting callers that
        genuinely need every row are unchanged; screens pass a page size."""
        return self._sale_repo.list_all(limit=limit, offset=offset)

    @require_permission(Permission.SALE_VIEW.value)
    def count_sales(self, actor_user_id: str) -> int:
        """Total for the pager, counted by the database rather than by
        loading every row and taking len()."""
        return self._sale_repo.count_all()

    @require_permission(Permission.SALE_VIEW.value)
    def get_sale(self, actor_user_id: str, sale_id: str) -> Sale:
        return self._get_sale_or_raise(sale_id)

    @require_permission(Permission.SALE_MANAGE.value)
    def cancel_sale(self, actor_user_id: str, sale_id: str, reason: str) -> Sale:
        """Cancel a sale, reverse its fuel and reverse its payment atomically.

        Same reasoning as create_sale: a cancellation that reversed the
        fuel but failed before reversing the payment would leave the
        books claiming money was collected for fuel that went back in the
        tank.
        """
        with unit_of_work(self._session):
            return self._cancel_sale_impl(actor_user_id, sale_id, reason)

    def _cancel_sale_impl(self, actor_user_id: str, sale_id: str, reason: str) -> Sale:
        if not reason or not reason.strip():
            raise ValueError("A reason is required to cancel a sale")

        sale = self._get_sale_or_raise(sale_id)
        if sale.status != SaleStatus.COMPLETED.value:
            raise ConflictError(f"Cannot cancel a sale with status {sale.status}")

        tank_id = sale.tank_transaction.tank_id if sale.tank_transaction else self._resolve_tank_id(sale.nozzle)
        reversal = self._tank_service.record_transaction_as_related_action(
            actor_user_id,
            tank_id,
            TankTransactionType.ADJUSTMENT,
            TankTransactionCreate(
                quantity=sale.quantity,
                reference=sale.receipt_number,
                remarks=f"Reversal of cancelled sale {sale.receipt_number}: {reason.strip()}",
            ),
        )

        sale.status = SaleStatus.CANCELLED.value
        sale.cancellation_reason = reason.strip()
        sale.reversal_transaction_id = reversal.id
        sale = self._sale_repo.update(sale)

        payment = self._payment_repo.get_by_sale_id(sale.id)
        if payment and payment.status not in (PaymentStatus.REVERSED.value, PaymentStatus.REFUNDED.value):
            payment.status = PaymentStatus.REVERSED.value
            payment.status_reason = f"Sale {sale.receipt_number} cancelled: {reason.strip()}"
            self._payment_repo.update(payment)

        self._audit_repo.record(
            event_type="sale_cancelled",
            actor_id=actor_user_id,
            entity_type="Sale",
            entity_id=sale.id,
            description=reason.strip(),
        )
        return sale

    # ------------------------------------------------------------------
    # Payments (problemstatement.md #17)
    # ------------------------------------------------------------------

    @require_permission(Permission.SALE_VIEW.value)
    def list_payments(self, actor_user_id: str, limit: Optional[int] = None, offset: int = 0) -> List[Payment]:
        return self._payment_repo.list_all(limit=limit, offset=offset)

    @require_permission(Permission.SALE_VIEW.value)
    def count_payments(self, actor_user_id: str) -> int:
        return self._payment_repo.count_all()

    @require_permission(Permission.SALE_VIEW.value)
    def get_payment_for_sale(self, actor_user_id: str, sale_id: str) -> Optional[Payment]:
        return self._payment_repo.get_by_sale_id(sale_id)

    @require_permission(Permission.SALE_MANAGE.value)
    def mark_payment_failed(self, actor_user_id: str, payment_id: str, reason: str) -> Payment:
        if not reason or not reason.strip():
            raise ValueError("A reason is required to mark a payment as failed")

        payment = self._get_payment_or_raise(payment_id)
        if payment.status != PaymentStatus.SUCCESS.value:
            raise ConflictError(f"Cannot mark a payment with status {payment.status} as failed")

        payment.status = PaymentStatus.FAILED.value
        payment.status_reason = reason.strip()
        payment = self._payment_repo.update(payment)

        self._audit_repo.record(
            event_type="payment_marked_failed",
            actor_id=actor_user_id,
            entity_type="Payment",
            entity_id=payment.id,
            description=reason.strip(),
        )
        return payment

    @require_permission(Permission.SALE_MANAGE.value)
    def refund_payment(self, actor_user_id: str, payment_id: str, reason: str) -> Payment:
        if not reason or not reason.strip():
            raise ValueError("A reason is required to refund a payment")

        payment = self._get_payment_or_raise(payment_id)
        if payment.status != PaymentStatus.SUCCESS.value:
            raise ConflictError(f"Cannot refund a payment with status {payment.status}")

        payment.status = PaymentStatus.REFUNDED.value
        payment.status_reason = reason.strip()
        payment = self._payment_repo.update(payment)

        self._audit_repo.record(
            event_type="payment_refunded",
            actor_id=actor_user_id,
            entity_type="Payment",
            entity_id=payment.id,
            description=reason.strip(),
        )
        return payment

    def _get_payment_or_raise(self, payment_id: str) -> Payment:
        payment = self._payment_repo.get_by_id(payment_id)
        if not payment:
            raise NotFoundError(f"Payment not found: {payment_id}")
        return payment

    # ------------------------------------------------------------------
    # Customers
    # ------------------------------------------------------------------

    @require_permission(Permission.SALE_MANAGE.value)
    def create_customer(self, actor_user_id: str, data: CustomerCreate) -> Customer:
        if self._customer_repo.get_by_name(data.name):
            raise ConflictError(f"A customer named {data.name!r} already exists")

        customer = Customer(
            name=data.name, phone=data.phone, email=data.email, address=data.address, status=StatusEnum.ACTIVE.value
        )
        customer = self._customer_repo.add(customer)
        self._audit_repo.record(
            event_type="customer_created",
            actor_id=actor_user_id,
            entity_type="Customer",
            entity_id=customer.id,
            description=f"Created customer {data.name}",
        )
        return customer

    @require_permission(Permission.SALE_VIEW.value)
    def list_customers(self, actor_user_id: str) -> List[Customer]:
        return self._customer_repo.list_all()

    @require_permission(Permission.SALE_MANAGE.value)
    def set_customer_status(self, actor_user_id: str, customer_id: str, status: StatusEnum, reason: str) -> Customer:
        if not reason or not reason.strip():
            raise ValueError("A reason is required to change a customer's status")

        customer = self._customer_repo.get_by_id(customer_id)
        if not customer:
            raise NotFoundError(f"Customer not found: {customer_id}")

        old_status = customer.status
        customer.status = status.value
        customer = self._customer_repo.update(customer)
        self._audit_repo.record(
            event_type="customer_status_changed",
            actor_id=actor_user_id,
            entity_type="Customer",
            entity_id=customer.id,
            description=reason.strip(),
            old_value=old_status,
            new_value=status.value,
        )
        return customer

    def _resolve_tank_id(self, nozzle) -> str:
        if nozzle.tank_id:
            return nozzle.tank_id
        active_tanks = [
            tank for tank in self._tank_repo.list_all() if tank.fuel_id == nozzle.fuel_id and tank.status == "active"
        ]
        if len(active_tanks) == 1:
            return active_tanks[0].id
        if not active_tanks:
            raise ConflictError("No active tank found for this nozzle's fuel type; configure the nozzle's tank")
        raise ConflictError(
            "More than one active tank exists for this nozzle's fuel type; configure the nozzle's tank explicitly"
        )

    def _get_sale_or_raise(self, sale_id: str) -> Sale:
        sale = self._sale_repo.get_by_id(sale_id)
        if not sale:
            raise NotFoundError(f"Sale not found: {sale_id}")
        return sale

"""Shift cash/UPI/card reconciliation (problemstatement.md #20/#21,
Phase 15). Fuel reconciliation already exists per-tank (Phase 9,
TankService.perform_reconciliation) and is intentionally not
duplicated here - this service covers the cash/UPI/card/expense side,
folded into one per-shift reconciliation rather than five separate
mechanisms, since they're all settled together at the same point
(shift close) against the same source data (that shift's Sales,
Payments, and approved Expenses).
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import List

from app.core.constants import (
    PaymentMethod,
    Permission,
    ReconciliationStatus,
    RECONCILIATION_VARIANCE_APPROVAL_THRESHOLD_PERCENT,
    RECONCILIATION_VARIANCE_INVESTIGATION_THRESHOLD_PERCENT,
    RECONCILIATION_VARIANCE_WARNING_THRESHOLD_PERCENT,
    SaleStatus,
    VarianceClassification,
)
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_permission
from app.models.shift_reconciliation import ShiftReconciliation
from app.schemas.shift_reconciliation import ShiftReconciliationPerform


def classify_reconciliation_variance(variance_percent: Decimal) -> VarianceClassification:
    magnitude = abs(float(variance_percent))
    if magnitude <= RECONCILIATION_VARIANCE_WARNING_THRESHOLD_PERCENT:
        return VarianceClassification.NORMAL
    if magnitude <= RECONCILIATION_VARIANCE_INVESTIGATION_THRESHOLD_PERCENT:
        return VarianceClassification.WARNING
    if magnitude <= RECONCILIATION_VARIANCE_APPROVAL_THRESHOLD_PERCENT:
        return VarianceClassification.INVESTIGATION_REQUIRED
    return VarianceClassification.APPROVAL_REQUIRED


_CLASSIFICATION_SEVERITY = {
    VarianceClassification.NORMAL: 0,
    VarianceClassification.WARNING: 1,
    VarianceClassification.INVESTIGATION_REQUIRED: 2,
    VarianceClassification.APPROVAL_REQUIRED: 3,
}


def _worst(classifications: List[VarianceClassification]) -> VarianceClassification:
    return max(classifications, key=lambda c: _CLASSIFICATION_SEVERITY[c])


def _variance_percent(variance: Decimal, expected: Decimal) -> Decimal:
    if expected != 0:
        return (variance / expected) * 100
    return Decimal("0") if variance == 0 else Decimal("100")


class ReconciliationService:
    def __init__(self, reconciliation_repo, shift_repo, sale_repo, expense_repo, audit_repo, auth_service):
        self._reconciliation_repo = reconciliation_repo
        self._shift_repo = shift_repo
        self._sale_repo = sale_repo
        self._expense_repo = expense_repo
        self._audit_repo = audit_repo
        self._auth_service = auth_service

    @require_permission(Permission.RECONCILIATION_MANAGE.value)
    def perform_shift_reconciliation(self, actor_user_id: str, data: ShiftReconciliationPerform) -> ShiftReconciliation:
        shift = self._shift_repo.get_by_id(data.shift_id)
        if not shift:
            raise NotFoundError(f"Shift not found: {data.shift_id}")
        if self._reconciliation_repo.get_by_shift_id(data.shift_id):
            raise ConflictError("This shift has already been reconciled")

        sales = [s for s in self._sale_repo.list_by_shift(data.shift_id) if s.status == SaleStatus.COMPLETED.value]
        expenses = [e for e in self._expense_repo.list_by_shift(data.shift_id) if e.status == "approved"]

        def sales_total(method: PaymentMethod) -> Decimal:
            return sum((s.amount for s in sales if s.payment_method == method.value), Decimal("0"))

        def expenses_total(method: PaymentMethod) -> Decimal:
            return sum((e.amount for e in expenses if e.payment_method == method.value), Decimal("0"))

        expected_cash = sales_total(PaymentMethod.CASH) - expenses_total(PaymentMethod.CASH)
        expected_upi = sales_total(PaymentMethod.UPI) - expenses_total(PaymentMethod.UPI)
        expected_card = sales_total(PaymentMethod.CARD) - expenses_total(PaymentMethod.CARD)

        cash_variance = data.declared_cash - expected_cash
        upi_variance = data.declared_upi - expected_upi
        card_variance = data.declared_card - expected_card

        classification = _worst(
            [
                classify_reconciliation_variance(_variance_percent(cash_variance, expected_cash)),
                classify_reconciliation_variance(_variance_percent(upi_variance, expected_upi)),
                classify_reconciliation_variance(_variance_percent(card_variance, expected_card)),
            ]
        )
        status = (
            ReconciliationStatus.ACCEPTED
            if classification in (VarianceClassification.NORMAL, VarianceClassification.WARNING)
            else ReconciliationStatus.PENDING_APPROVAL
        )

        reconciliation = ShiftReconciliation(
            shift_id=data.shift_id,
            expected_cash=expected_cash,
            declared_cash=data.declared_cash,
            cash_variance=cash_variance,
            expected_upi=expected_upi,
            declared_upi=data.declared_upi,
            upi_variance=upi_variance,
            expected_card=expected_card,
            declared_card=data.declared_card,
            card_variance=card_variance,
            classification=classification.value,
            status=status.value,
            performed_by_id=actor_user_id,
            remarks=data.remarks,
        )
        reconciliation = self._reconciliation_repo.add(reconciliation)

        self._audit_repo.record(
            event_type="shift_reconciliation_performed",
            actor_id=actor_user_id,
            entity_type="ShiftReconciliation",
            entity_id=reconciliation.id,
            description=(
                f"Reconciled shift {shift.shift_date} {shift.shift_label}: "
                f"cash variance {cash_variance:.2f}, UPI variance {upi_variance:.2f}, "
                f"card variance {card_variance:.2f} ({classification.value})"
            ),
        )
        return reconciliation

    @require_permission(Permission.RECONCILIATION_APPROVE.value)
    def approve_shift_reconciliation(self, actor_user_id: str, reconciliation_id: str, remarks: str = "") -> ShiftReconciliation:
        reconciliation = self._get_or_raise(reconciliation_id)
        if reconciliation.status != ReconciliationStatus.PENDING_APPROVAL.value:
            raise ConflictError(f"Cannot approve a reconciliation with status {reconciliation.status}")

        reconciliation.status = ReconciliationStatus.APPROVED.value
        reconciliation.approved_by_id = actor_user_id
        reconciliation.approved_at = datetime.now(timezone.utc)
        reconciliation.approval_remarks = remarks.strip() or None
        reconciliation = self._reconciliation_repo.update(reconciliation)

        self._audit_repo.record(
            event_type="shift_reconciliation_approved",
            actor_id=actor_user_id,
            entity_type="ShiftReconciliation",
            entity_id=reconciliation.id,
            description=remarks.strip() or "Approved",
        )
        return reconciliation

    @require_permission(Permission.RECONCILIATION_VIEW.value)
    def list_reconciliations(self, actor_user_id: str) -> List[ShiftReconciliation]:
        return self._reconciliation_repo.list_all()

    @require_permission(Permission.RECONCILIATION_VIEW.value)
    def get_for_shift(self, actor_user_id: str, shift_id: str):
        return self._reconciliation_repo.get_by_shift_id(shift_id)

    def _get_or_raise(self, reconciliation_id: str) -> ShiftReconciliation:
        reconciliation = self._reconciliation_repo.get_by_id(reconciliation_id)
        if not reconciliation:
            raise NotFoundError(f"Reconciliation not found: {reconciliation_id}")
        return reconciliation

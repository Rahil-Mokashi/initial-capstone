"""Shift tender reconciliation (problemstatement.md #20/#21, Phase 15;
reshaped from a fixed cash/UPI/card model to per-tender lines in
PROJECT_CONTEXT.md's Step 2 - see ShiftReconciliationLine). Fuel
reconciliation already exists per-tank (Phase 9, TankService.
perform_reconciliation) and is intentionally not duplicated here - this
service covers the tender/expense side, folded into one per-shift
reconciliation rather than one mechanism per tender, since they're all
settled together at the same point (shift close) against the same
source data (that shift's Sales and approved Expenses).
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Tuple

from app.core.constants import (
    Permission,
    ReconciliationStatus,
    RECONCILIATION_VARIANCE_APPROVAL_THRESHOLD_PERCENT,
    RECONCILIATION_VARIANCE_INVESTIGATION_THRESHOLD_PERCENT,
    RECONCILIATION_VARIANCE_WARNING_THRESHOLD_PERCENT,
    SaleStatus,
    TenderSettlementType,
    VarianceClassification,
)
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_permission
from app.repositories.base import session_for, unit_of_work
from app.models.shift_reconciliation import ShiftReconciliation
from app.models.shift_reconciliation_line import ShiftReconciliationLine
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
    def __init__(self, reconciliation_repo, shift_repo, sale_repo, expense_repo, audit_repo, auth_service, tender_repo):
        self._reconciliation_repo = reconciliation_repo
        self._shift_repo = shift_repo
        self._sale_repo = sale_repo
        self._expense_repo = expense_repo
        self._audit_repo = audit_repo
        self._auth_service = auth_service
        # Required, not optional (unlike SaleService/ExpenseService's
        # tender_repo=None): this service's entire job is now per-tender
        # reconciliation, so it cannot meaningfully run without one.
        self._tender_repo = tender_repo
        self._session = session_for(reconciliation_repo)

    @require_permission(Permission.RECONCILIATION_VIEW.value)
    def get_expected_amounts_for_shift(self, actor_user_id: str, shift_id: str) -> List[Tuple[object, Decimal]]:
        """(Tender, expected amount) for every non-credit tender with
        actual expected activity this shift - what the UI renders one
        declared-amount input for, and what perform_shift_reconciliation
        requires a declaration for. A tender with zero expected activity
        (no sales, no expenses) is left out entirely, which is why a
        typical shift today still produces ~3 entries (Cash, Card,
        Other) even though 8 tenders exist - see Tender's own docstring.
        Returns real Tender objects, not bare ids, so the UI has a name
        to label each input with without a second lookup.
        """
        if not self._shift_repo.get_by_id(shift_id):
            raise NotFoundError(f"Shift not found: {shift_id}")
        return self._expected_amounts(shift_id)

    def _expected_amounts(self, shift_id: str) -> List[Tuple[object, Decimal]]:
        sales = [s for s in self._sale_repo.list_by_shift(shift_id) if s.status == SaleStatus.COMPLETED.value]
        expenses = [e for e in self._expense_repo.list_by_shift(shift_id) if e.status == "approved"]

        expected_by_tender_id: Dict[str, Decimal] = {}
        for sale in sales:
            if sale.tender_id:
                expected_by_tender_id[sale.tender_id] = expected_by_tender_id.get(sale.tender_id, Decimal("0")) + sale.amount
        for expense in expenses:
            if expense.tender_id:
                expected_by_tender_id[expense.tender_id] = expected_by_tender_id.get(expense.tender_id, Decimal("0")) - expense.amount

        # Credit is never collected at the point of sale (it's tracked
        # separately via CreditService) - excluded here the same way it
        # was never part of the old cash/upi/card columns either.
        results = []
        for tender_id, amount in expected_by_tender_id.items():
            if amount == 0:
                continue
            tender = self._tender_repo.get_by_id(tender_id)
            if tender is None or tender.settlement_type == TenderSettlementType.INVOICED_CREDIT.value:
                continue
            results.append((tender, amount))
        return results

    @require_permission(Permission.RECONCILIATION_MANAGE.value)
    def perform_shift_reconciliation(self, actor_user_id: str, data: ShiftReconciliationPerform) -> ShiftReconciliation:
        """Computes expected against declared for every tender with
        activity that shift and writes the result as one record plus
        one line per tender. Wrapped in a transaction so a failure can
        never leave a shift half-reconciled."""
        with unit_of_work(self._session):
            return self._perform_shift_reconciliation_impl(actor_user_id, data)

    def _perform_shift_reconciliation_impl(self, actor_user_id: str, data: ShiftReconciliationPerform):
        shift = self._shift_repo.get_by_id(data.shift_id)
        if not shift:
            raise NotFoundError(f"Shift not found: {data.shift_id}")
        if self._reconciliation_repo.get_by_shift_id(data.shift_id):
            raise ConflictError("This shift has already been reconciled")

        expected_amounts = self._expected_amounts(data.shift_id)
        missing = [tender for tender, _ in expected_amounts if tender.id not in data.declared_amounts]
        if missing:
            names = ", ".join(sorted(t.name for t in missing))
            raise ValueError(f"A declared amount is required for every tender with activity this shift: {names}")

        # Computed before the reconciliation row is created, so it can be
        # written once with its real classification/status rather than a
        # placeholder immediately overwritten - each line needs the
        # row's id as a foreign key, but nothing about classification
        # depends on the row existing first.
        lines_to_create = []
        classifications = []
        line_descriptions = []
        for tender, expected in expected_amounts:
            declared = data.declared_amounts[tender.id]
            variance = declared - expected
            lines_to_create.append((tender.id, expected, declared, variance))
            classifications.append(classify_reconciliation_variance(_variance_percent(variance, expected)))
            line_descriptions.append(f"{tender.name} variance {variance:.2f}")

        classification = _worst(classifications) if classifications else VarianceClassification.NORMAL
        status = (
            ReconciliationStatus.ACCEPTED
            if classification in (VarianceClassification.NORMAL, VarianceClassification.WARNING)
            else ReconciliationStatus.PENDING_APPROVAL
        )

        reconciliation = ShiftReconciliation(
            shift_id=data.shift_id,
            classification=classification.value,
            status=status.value,
            performed_by_id=actor_user_id,
            remarks=data.remarks,
        )
        reconciliation = self._reconciliation_repo.add(reconciliation)

        for tender_id, expected, declared, variance in lines_to_create:
            self._session.add(ShiftReconciliationLine(
                shift_reconciliation_id=reconciliation.id,
                tender_id=tender_id,
                expected=expected,
                declared=declared,
                variance=variance,
            ))
        self._session.flush()

        self._audit_repo.record(
            event_type="shift_reconciliation_performed",
            actor_id=actor_user_id,
            entity_type="ShiftReconciliation",
            entity_id=reconciliation.id,
            description=(
                f"Reconciled shift {shift.shift_date} {shift.shift_label}: "
                f"{'; '.join(line_descriptions) if line_descriptions else 'no tenders had activity'} "
                f"({classification.value})"
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

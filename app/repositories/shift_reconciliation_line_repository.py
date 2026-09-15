from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.constants import TenderSettlementType
from app.models.employee_cash_shortage import EmployeeCashShortage
from app.models.shift_reconciliation_line import ShiftReconciliationLine
from app.models.tender import Tender


class ShiftReconciliationLineRepository:
    """Lines are normally reached through ShiftReconciliation.lines (see
    that model's own docstring); this exists for the two things that
    need lines directly rather than through their parent reconciliation
    - EmployeeShortageService.record_shortage (handed a line id) and its
    "which lines still need a shortage recorded" dropdown source."""

    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, line_id: str) -> Optional[ShiftReconciliationLine]:
        return self._session.query(ShiftReconciliationLine).filter_by(id=line_id).first()

    def list_unbooked_shortage_candidates(self) -> List[ShiftReconciliationLine]:
        """Every line with a genuine, not-yet-booked cash shortage: a
        negative variance on an immediate-cash tender that no
        EmployeeCashShortage has claimed yet (the outer join's IS NULL
        check) - exactly what EmployeeShortageService.record_shortage
        itself validates, kept in sync so the UI never offers a line the
        service would then reject."""
        return (
            self._session.query(ShiftReconciliationLine)
            .join(Tender, ShiftReconciliationLine.tender_id == Tender.id)
            .outerjoin(
                EmployeeCashShortage,
                EmployeeCashShortage.shift_reconciliation_line_id == ShiftReconciliationLine.id,
            )
            .filter(
                Tender.settlement_type == TenderSettlementType.IMMEDIATE_CASH.value,
                ShiftReconciliationLine.variance < 0,
                EmployeeCashShortage.id.is_(None),
            )
            .all()
        )

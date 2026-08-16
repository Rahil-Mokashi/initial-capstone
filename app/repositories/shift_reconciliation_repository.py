from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.shift_reconciliation import ShiftReconciliation
from app.repositories.base import safe_commit


class ShiftReconciliationRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, reconciliation_id: str) -> Optional[ShiftReconciliation]:
        return self._session.query(ShiftReconciliation).filter_by(id=reconciliation_id).first()

    def get_by_shift_id(self, shift_id: str) -> Optional[ShiftReconciliation]:
        return self._session.query(ShiftReconciliation).filter_by(shift_id=shift_id).first()

    def list_all(self) -> List[ShiftReconciliation]:
        return self._session.query(ShiftReconciliation).order_by(ShiftReconciliation.performed_at.desc()).all()

    def add(self, reconciliation: ShiftReconciliation) -> ShiftReconciliation:
        self._session.add(reconciliation)
        safe_commit(self._session)
        self._session.refresh(reconciliation)
        return reconciliation

    def update(self, reconciliation: ShiftReconciliation) -> ShiftReconciliation:
        safe_commit(self._session)
        self._session.refresh(reconciliation)
        return reconciliation

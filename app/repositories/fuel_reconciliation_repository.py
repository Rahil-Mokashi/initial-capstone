from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.fuel_reconciliation import FuelReconciliation
from app.repositories.base import safe_commit


class FuelReconciliationRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, reconciliation_id: str) -> Optional[FuelReconciliation]:
        return self._session.query(FuelReconciliation).filter_by(id=reconciliation_id).first()

    def list_for_tank(self, tank_id: str) -> List[FuelReconciliation]:
        return (
            self._session.query(FuelReconciliation)
            .filter_by(tank_id=tank_id)
            .order_by(FuelReconciliation.reconciliation_date.desc())
            .all()
        )

    def get_latest_for_tank(self, tank_id: str) -> Optional[FuelReconciliation]:
        return (
            self._session.query(FuelReconciliation)
            .filter_by(tank_id=tank_id)
            .order_by(FuelReconciliation.reconciliation_date.desc())
            .first()
        )

    def add(self, reconciliation: FuelReconciliation) -> FuelReconciliation:
        self._session.add(reconciliation)
        safe_commit(self._session)
        self._session.refresh(reconciliation)
        return reconciliation

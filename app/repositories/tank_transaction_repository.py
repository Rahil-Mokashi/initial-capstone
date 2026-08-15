from datetime import date, datetime, time
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.tank_transaction import TankTransaction
from app.repositories.base import safe_commit


class TankTransactionRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, transaction_id: str) -> Optional[TankTransaction]:
        return self._session.query(TankTransaction).filter_by(id=transaction_id).first()

    def list_for_tank(self, tank_id: str) -> List[TankTransaction]:
        return (
            self._session.query(TankTransaction)
            .filter_by(tank_id=tank_id)
            .order_by(TankTransaction.transaction_at.desc())
            .all()
        )

    def sum_for_tank_by_type(
        self, tank_id: str, transaction_type: str, date_from: Optional[date] = None, date_to: Optional[date] = None
    ) -> float:
        """date_from/date_to are calendar dates; widened to the full day so a
        transaction recorded on date_to itself (with a time component) isn't
        excluded by a naive date<->datetime comparison."""
        query = self._session.query(TankTransaction).filter_by(tank_id=tank_id, transaction_type=transaction_type)
        if date_from:
            query = query.filter(TankTransaction.transaction_at >= datetime.combine(date_from, time.min))
        if date_to:
            query = query.filter(TankTransaction.transaction_at <= datetime.combine(date_to, time.max))
        return sum(t.quantity for t in query.all())

    def add(self, transaction: TankTransaction) -> TankTransaction:
        self._session.add(transaction)
        safe_commit(self._session)
        self._session.refresh(transaction)
        return transaction

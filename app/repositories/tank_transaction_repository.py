from datetime import date, datetime, time, timezone
from decimal import Decimal
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

    def list_recent(self, limit: int = 10) -> List[TankTransaction]:
        """Newest first, across every tank - for a dashboard/list-page
        activity feed rather than one specific tank's own history."""
        return (
            self._session.query(TankTransaction)
            .order_by(TankTransaction.transaction_at.desc())
            .limit(limit)
            .all()
        )

    def sum_for_tank_by_type(
        self, tank_id: str, transaction_type: str, date_from: Optional[date] = None, date_to: Optional[date] = None
    ) -> Decimal:
        """date_from/date_to are local calendar dates; widened to the full
        local day, then converted to UTC-aware instants before comparing
        against transaction_at (stored UTC-aware) — a naive local-midnight
        boundary compared directly against a UTC timestamp silently drops
        transactions recorded after local midnight whenever local time runs
        ahead of UTC (e.g. IST, UTC+5:30)."""
        query = self._session.query(TankTransaction).filter_by(tank_id=tank_id, transaction_type=transaction_type)
        if date_from:
            start_of_day = datetime.combine(date_from, time.min).astimezone(timezone.utc)
            query = query.filter(TankTransaction.transaction_at >= start_of_day)
        if date_to:
            end_of_day = datetime.combine(date_to, time.max).astimezone(timezone.utc)
            query = query.filter(TankTransaction.transaction_at <= end_of_day)
        return sum((t.quantity for t in query.all()), Decimal("0"))

    def add(self, transaction: TankTransaction) -> TankTransaction:
        self._session.add(transaction)
        safe_commit(self._session)
        self._session.refresh(transaction)
        return transaction

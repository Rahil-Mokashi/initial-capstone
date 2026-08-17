from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.fuel_price_history import FuelPriceHistory
from app.repositories.base import safe_commit


class FuelPriceHistoryRepository:
    """Append-only: there is deliberately no update() or delete()."""

    def __init__(self, session: Session):
        self._session = session

    def add(self, entry: FuelPriceHistory) -> FuelPriceHistory:
        self._session.add(entry)
        safe_commit(self._session)
        self._session.refresh(entry)
        return entry

    def list_for_fuel(self, fuel_id: str) -> List[FuelPriceHistory]:
        return (
            self._session.query(FuelPriceHistory)
            .filter_by(fuel_id=fuel_id)
            .order_by(FuelPriceHistory.effective_from.desc())
            .all()
        )

    def list_all(self) -> List[FuelPriceHistory]:
        return (
            self._session.query(FuelPriceHistory)
            .order_by(FuelPriceHistory.effective_from.desc())
            .all()
        )

    def get_latest_for_fuel(self, fuel_id: str) -> Optional[FuelPriceHistory]:
        return (
            self._session.query(FuelPriceHistory)
            .filter_by(fuel_id=fuel_id)
            .order_by(FuelPriceHistory.effective_from.desc())
            .first()
        )

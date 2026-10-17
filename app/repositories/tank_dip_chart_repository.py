from datetime import datetime, timezone
from typing import List

from sqlalchemy.orm import Session

from app.models.tank_dip_chart import TankDipChartPoint
from app.repositories.base import safe_commit


class TankDipChartRepository:
    def __init__(self, session: Session):
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def active_points(self, tank_id: str) -> List[TankDipChartPoint]:
        return (
            self._session.query(TankDipChartPoint)
            .filter(TankDipChartPoint.tank_id == tank_id, TankDipChartPoint.voided_at.is_(None))
            .order_by(TankDipChartPoint.dip_cm)
            .all()
        )

    def void_active(self, tank_id: str) -> int:
        rows = self.active_points(tank_id)
        now = datetime.now(timezone.utc)
        for r in rows:
            r.voided_at = now
        return len(rows)

    def add_all(self, rows: List[TankDipChartPoint]) -> None:
        self._session.add_all(rows)
        safe_commit(self._session)

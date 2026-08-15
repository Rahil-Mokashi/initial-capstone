from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.tank_reading import TankReading
from app.repositories.base import safe_commit


class TankReadingRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, reading_id: str) -> Optional[TankReading]:
        return self._session.query(TankReading).filter_by(id=reading_id).first()

    def list_for_tank(self, tank_id: str) -> List[TankReading]:
        return (
            self._session.query(TankReading)
            .filter_by(tank_id=tank_id)
            .order_by(TankReading.reading_at.desc())
            .all()
        )

    def get_latest_for_tank(self, tank_id: str) -> Optional[TankReading]:
        return (
            self._session.query(TankReading)
            .filter_by(tank_id=tank_id)
            .order_by(TankReading.reading_at.desc())
            .first()
        )

    def add(self, reading: TankReading) -> TankReading:
        self._session.add(reading)
        safe_commit(self._session)
        self._session.refresh(reading)
        return reading

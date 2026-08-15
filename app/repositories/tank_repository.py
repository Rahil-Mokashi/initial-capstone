from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.tank import Tank
from app.repositories.base import safe_commit


class TankRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, tank_id: str) -> Optional[Tank]:
        return self._session.query(Tank).filter_by(id=tank_id, is_deleted=False).first()

    def get_by_code(self, code: str) -> Optional[Tank]:
        return self._session.query(Tank).filter_by(code=code, is_deleted=False).first()

    def list_all(self) -> List[Tank]:
        return self._session.query(Tank).filter_by(is_deleted=False).all()

    def add(self, tank: Tank) -> Tank:
        self._session.add(tank)
        safe_commit(self._session)
        self._session.refresh(tank)
        return tank

    def update(self, tank: Tank) -> Tank:
        safe_commit(self._session)
        self._session.refresh(tank)
        return tank

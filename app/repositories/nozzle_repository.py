from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.nozzle import Nozzle
from app.repositories.base import safe_commit


class NozzleRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, nozzle_id: str) -> Optional[Nozzle]:
        return self._session.query(Nozzle).filter_by(id=nozzle_id, is_deleted=False).first()

    def get_by_code(self, code: str) -> Optional[Nozzle]:
        return self._session.query(Nozzle).filter_by(code=code, is_deleted=False).first()

    def list_all(self) -> List[Nozzle]:
        return self._session.query(Nozzle).filter_by(is_deleted=False).all()

    def list_active(self) -> List[Nozzle]:
        return self._session.query(Nozzle).filter_by(is_deleted=False, status="active").all()

    def list_for_dispenser(self, dispenser_id: str) -> List[Nozzle]:
        return self._session.query(Nozzle).filter_by(is_deleted=False, dispenser_id=dispenser_id).all()

    def add(self, nozzle: Nozzle) -> Nozzle:
        self._session.add(nozzle)
        safe_commit(self._session)
        self._session.refresh(nozzle)
        return nozzle

    def update(self, nozzle: Nozzle) -> Nozzle:
        safe_commit(self._session)
        self._session.refresh(nozzle)
        return nozzle

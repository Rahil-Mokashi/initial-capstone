from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.dispenser import Dispenser
from app.repositories.base import safe_commit


class DispenserRepository:
    """Minimal read/create access. See NozzleRepository for scope notes."""

    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, dispenser_id: str) -> Optional[Dispenser]:
        return self._session.query(Dispenser).filter_by(id=dispenser_id, is_deleted=False).first()

    def list_all(self) -> List[Dispenser]:
        return self._session.query(Dispenser).filter_by(is_deleted=False).all()

    def add(self, dispenser: Dispenser) -> Dispenser:
        self._session.add(dispenser)
        safe_commit(self._session)
        self._session.refresh(dispenser)
        return dispenser

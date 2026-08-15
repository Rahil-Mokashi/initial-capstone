from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.nozzle import Nozzle
from app.repositories.base import safe_commit


class NozzleRepository:
    """Minimal read access needed by ShiftService.

    Full nozzle master-data management (create/edit/status/UI) belongs to
    Phase 8 (Nozzle Management) — not built yet.
    """

    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, nozzle_id: str) -> Optional[Nozzle]:
        return self._session.query(Nozzle).filter_by(id=nozzle_id, is_deleted=False).first()

    def list_active(self) -> List[Nozzle]:
        return self._session.query(Nozzle).filter_by(is_deleted=False, status="active").all()

    def add(self, nozzle: Nozzle) -> Nozzle:
        self._session.add(nozzle)
        safe_commit(self._session)
        self._session.refresh(nozzle)
        return nozzle

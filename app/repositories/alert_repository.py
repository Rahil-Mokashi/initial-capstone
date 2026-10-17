from typing import List, Set

from sqlalchemy.orm import Session

from app.models.alert_acknowledgement import AlertAcknowledgement
from app.repositories.base import safe_commit


class AlertAcknowledgementRepository:
    """Insert and read only."""

    def __init__(self, session: Session):
        self._session = session

    def add(self, row: AlertAcknowledgement) -> AlertAcknowledgement:
        self._session.add(row)
        safe_commit(self._session)
        self._session.refresh(row)
        return row

    def keys_for_day_suffix(self, suffix: str) -> Set[str]:
        return {k for (k,) in self._session.query(AlertAcknowledgement.alert_key).filter(AlertAcknowledgement.alert_key.like(f"%{suffix}")).all()}

    def list_recent(self, limit: int = 200) -> List[AlertAcknowledgement]:
        return self._session.query(AlertAcknowledgement).order_by(AlertAcknowledgement.acknowledged_at.desc()).limit(limit).all()

    @property
    def session(self) -> Session:
        return self._session

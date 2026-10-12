from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.models.pump_setting import PumpSetting
from app.repositories.base import safe_commit


class PumpSettingRepository:
    def __init__(self, session: Session):
        self._session = session

    def all(self) -> Dict[str, str]:
        return {s.key: s.value for s in self._session.query(PumpSetting).all()}

    def get(self, key: str) -> Optional[PumpSetting]:
        return self._session.get(PumpSetting, key)

    def put(self, key: str, value: str, user_id: Optional[str]) -> PumpSetting:
        row = self.get(key)
        if row is None:
            row = PumpSetting(key=key, value=value, updated_by_id=user_id)
            self._session.add(row)
        else:
            row.value = value
            row.updated_by_id = user_id
        safe_commit(self._session)
        self._session.refresh(row)
        return row

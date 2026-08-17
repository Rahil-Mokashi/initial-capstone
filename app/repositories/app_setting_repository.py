from typing import Optional

from sqlalchemy.orm import Session

from app.models.app_setting import AppSetting
from app.repositories.base import safe_commit


class AppSettingRepository:
    """Single-row table: get_or_create is the only sensible read."""

    def __init__(self, session: Session):
        self._session = session

    def get_or_create(self) -> AppSetting:
        """Return the settings row, creating an empty one on first use.

        Creating on read rather than at seed time means an existing
        installation upgrading into this feature gets a row the first time
        anyone opens Settings, with no migration data step needed.
        """
        setting = self._session.query(AppSetting).first()
        if setting is None:
            setting = AppSetting()
            self._session.add(setting)
            safe_commit(self._session)
            self._session.refresh(setting)
        return setting

    def update(self, setting: AppSetting) -> AppSetting:
        safe_commit(self._session)
        self._session.refresh(setting)
        return setting

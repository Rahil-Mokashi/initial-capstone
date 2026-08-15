from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.security import hash_token
from app.models.user_session import UserSession


class UserSessionRepository:
    def __init__(self, session: Session):
        self._session = session

    def create(self, user_id: str, token: str, expires_at: datetime, device_info: Optional[str] = None) -> UserSession:
        entry = UserSession(
            user_id=user_id,
            token_hash=hash_token(token),
            expires_at=expires_at,
            device_info=device_info,
        )
        self._session.add(entry)
        self._session.commit()
        self._session.refresh(entry)
        return entry

    def get_by_token(self, token: str) -> Optional[UserSession]:
        return (
            self._session.query(UserSession)
            .filter_by(token_hash=hash_token(token), is_active=True)
            .first()
        )

    def touch(self, session_entry: UserSession) -> UserSession:
        session_entry.last_activity_at = datetime.now(timezone.utc)
        self._session.commit()
        self._session.refresh(session_entry)
        return session_entry

    def invalidate(self, session_entry: UserSession) -> UserSession:
        session_entry.is_active = False
        self._session.commit()
        self._session.refresh(session_entry)
        return session_entry

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship
from app.database.types import UtcDateTime

from .base import Base


class UserSession(Base):
    """Tracks an active login session so it can be validated and auto-expired."""

    __tablename__ = "user_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(UtcDateTime, nullable=False)
    last_activity_at = Column(UtcDateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    device_info = Column(String(256), nullable=True)

    user = relationship("User")

    def __repr__(self) -> str:
        return f"<UserSession(user_id={self.user_id!r}, is_active={self.is_active!r})>"

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship
from app.database.types import UtcDateTime

from .base import Base


class AuditLog(Base):
    """Immutable audit trail record (problemstatement.md #40).

    Audit records are append-only: there is deliberately no updated_at or
    is_deleted column, and no repository update/delete method exists for
    this model. Historical financial and security data must never be
    silently changed.
    """

    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type = Column(String(64), nullable=False, index=True)
    actor_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    entity_type = Column(String(64), nullable=True)
    entity_id = Column(String(36), nullable=True)
    description = Column(Text, nullable=True)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    device_info = Column(String(256), nullable=True)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    actor = relationship("User")

    def __repr__(self) -> str:
        return f"<AuditLog(event_type={self.event_type!r}, actor_id={self.actor_id!r})>"

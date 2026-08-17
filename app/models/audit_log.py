import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, String, Text
from sqlalchemy.orm import relationship
from app.database.types import UtcDateTime

from .base import Base


class AuditLog(Base):
    """Immutable audit trail record (problemstatement.md #40).

    Audit records are append-only: there is deliberately no updated_at or
    is_deleted column, and no repository update/delete method exists for
    this model. Historical financial and security data must never be
    silently changed.

    That is enforced at two levels beyond convention: database triggers
    reject any UPDATE or DELETE against this table (so even direct SQL
    fails), and each row carries a hash chaining it to its predecessor so
    tampering that bypassed the triggers is still detectable. See the
    previous_hash/entry_hash columns below.
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

    # --- Tamper-evidence -------------------------------------------------
    # "Append-only" was true only by convention: no code updates or deletes
    # these rows, but the .db file sits on a forecourt PC and anyone with a
    # DB browser could rewrite the trail, and nobody could tell.
    #
    # Preventing modification outright needs append-only storage you do not
    # control, which an offline desktop app does not have. What IS
    # achievable is making modification DETECTABLE, and the distinction
    # between tamper-resistant and tamper-evident is worth being precise
    # about.
    #
    # Each row stores SHA-256 over its own fields plus the previous row's
    # hash, so every entry commits to the whole history before it. Altering
    # or removing any row breaks the chain from that point on, and a
    # verification pass finds it. This is the same construction as a
    # blockchain minus the distributed consensus - which is the part that
    # would be doing nothing useful on a single machine.
    previous_hash = Column(String(64), nullable=True)
    entry_hash = Column(String(64), nullable=True, index=True)

    actor = relationship("User")

    def __repr__(self) -> str:
        return f"<AuditLog(event_type={self.event_type!r}, actor_id={self.actor_id!r})>"

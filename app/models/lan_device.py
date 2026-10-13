"""A PC enrolled to talk to the Main PC over the pump's network (docs/adr-lan-multi-user.md).

Rows are never deleted: revoking a device stamps revoked_at/revoked_by_id so the history of which PC could reach the data stays.
Only a hash of the device token is stored.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, String

from app.database.types import UtcDateTime

from .base import Base


class LanDevice(Base):
    __tablename__ = "lan_devices"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(80), nullable=False, index=True)
    cert_serial = Column(String(64), nullable=False, unique=True)
    cert_fingerprint = Column(String(64), nullable=False)
    token_hash = Column(String(64), nullable=False, index=True)
    enrolled_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    enrolled_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    enrolled_ip = Column(String(45), nullable=True)
    last_seen_at = Column(UtcDateTime, nullable=True)
    last_ip = Column(String(45), nullable=True)
    revoked_at = Column(UtcDateTime, nullable=True, index=True)
    revoked_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    revoke_reason = Column(String(200), nullable=True)

    def __repr__(self) -> str:
        return f"<LanDevice({self.name!r}, revoked={self.revoked_at is not None})>"

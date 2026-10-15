"""One run of a Main PC safety check: database integrity, audit-chain verification, a backup, an off-device copy (LAN build, Phase 7).

Append-only: a failed run stays on record after a later good one, so the owner can see that something went wrong and when.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, String

from app.database.types import UtcDateTime

from .base import Base


class HealthRun(Base):
    __tablename__ = "health_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    kind = Column(String(16), nullable=False, index=True)  # integrity | audit_chain | backup | offsite
    ok = Column(Boolean, nullable=False)
    detail = Column(String(300), nullable=True)
    at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

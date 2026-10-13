"""Version numbers for two people editing one record at once (LAN build, Phase 3).

The Main PC counts every successful change to a record (`<collection>/<id>`, for example `employees/<uuid>`). A Client PC that read
version 4 and then tries to save is refused if the record is by now at version 5: it is told who changed it and when, reloads, and
makes its change again. Nobody's work is silently overwritten. The counter is an ordinary table so it survives restarts and travels
with backups; it is only written on a Main PC.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, Integer, String

from app.database.types import UtcDateTime

from .base import Base


class RecordVersion(Base):
    __tablename__ = "record_versions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    resource = Column(String(120), nullable=False, unique=True, index=True)
    version = Column(Integer, nullable=False, default=0)
    changed_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    changed_by_name = Column(String(120), nullable=True)
    changed_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

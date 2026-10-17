"""An alert somebody has seen and set aside, with who and when and why (append-only: there is no update or delete).

Alerts themselves are worked out from live data, so an alert whose problem is fixed simply stops appearing. Acknowledging is for the
ones that stay true (a note that it is known) and hides it for the rest of that business day; if the problem is still there tomorrow
it shows again. The key is stable for the same alert about the same record on the same day. An acknowledgement never changes a check
result, so the lock guard still sees a failing check as failing.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, String, Text

from app.database.types import UtcDateTime

from .base import Base


class AlertAcknowledgement(Base):
    __tablename__ = "alert_acknowledgements"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    alert_key = Column(String(64), nullable=False, index=True)
    category = Column(String(32), nullable=False)
    title = Column(String(300), nullable=False)
    reason = Column(Text, nullable=False)
    acknowledged_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    acknowledged_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

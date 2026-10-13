"""A day's daily report finalised by a person: the short hash of what it printed, who and when (append-only)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Date, ForeignKey, String

from app.database.types import UtcDateTime

from .base import Base


class DailyReportFinal(Base):
    __tablename__ = "daily_report_finals"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    report_date = Column(Date, nullable=False, index=True)
    style = Column(String(8), nullable=False)
    content_hash = Column(String(16), nullable=False)
    finalised_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    finalised_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

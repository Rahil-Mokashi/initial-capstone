"""An owner's "I have looked at this day" mark on the daily digest (LAN build, Phase 5).

One row per owner per day. Rows are never changed or deleted; looking again does not move the first mark.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database.types import UtcDateTime

from .base import Base


class DigestReview(Base):
    __tablename__ = "digest_reviews"
    __table_args__ = (UniqueConstraint("day", "user_id", name="uq_digest_reviews_day_user"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    day = Column(Date, nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    reviewed_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User")

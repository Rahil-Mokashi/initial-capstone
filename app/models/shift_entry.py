"""Where a shift's entry stands in the review chain: Entered -> Verified -> Approved -> Locked (LAN build, Phase 4).

One ShiftEntry per shift. The history is append-only: every change of state adds a ShiftEntryEvent (who, when, why) and
nothing is ever updated or deleted there, so how a figure came to be locked stays visible. A locked shift cannot be changed:
a correction is a recorded REOPEN with a reason by an owner, after which the chain starts again.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.database.types import UtcDateTime

from .base import Base

ENTERED, VERIFIED, APPROVED, LOCKED = "entered", "verified", "approved", "locked"


class ShiftEntry(Base):
    __tablename__ = "shift_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    shift_id = Column(String(36), ForeignKey("shifts.id"), nullable=False, unique=True, index=True)
    status = Column(String(12), nullable=False, default=ENTERED, index=True)
    updated_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    shift = relationship("Shift")
    events = relationship("ShiftEntryEvent", back_populates="entry", order_by="ShiftEntryEvent.at")


class ShiftEntryEvent(Base):
    __tablename__ = "shift_entry_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    shift_entry_id = Column(String(36), ForeignKey("shift_entries.id"), nullable=False, index=True)
    from_status = Column(String(12), nullable=True)
    to_status = Column(String(12), nullable=False)
    # entered | verified | approved | locked | reopened | data_changed
    action = Column(String(16), nullable=False)
    by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)  # null: the system (data changed after verifying)
    at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    reason = Column(Text, nullable=True)

    entry = relationship("ShiftEntry", back_populates="events")
    by = relationship("User")

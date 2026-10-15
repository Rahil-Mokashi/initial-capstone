"""Messages waiting to be sent to the owners (LAN build, Phase 6: the optional, outbound-only daily summary).

An outbox, not a log of sent mail: a row is created when a summary is due and the sender works through pending rows in its own thread, so
a mail server that is down or slow can never hold up anything else. One summary per kind per day (the unique key). Nothing in a row is
secret: the message carries only figures, never names, and the mail password is never stored here.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Date, Integer, String, Text, UniqueConstraint

from app.database.types import UtcDateTime

from .base import Base


class MailOutbox(Base):
    __tablename__ = "mail_outbox"
    __table_args__ = (UniqueConstraint("kind", "day", name="uq_mail_outbox_kind_day"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    kind = Column(String(24), nullable=False)  # daily_summary
    day = Column(Date, nullable=False, index=True)
    to_addrs = Column(String(400), nullable=False)
    subject = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String(10), nullable=False, default="pending", index=True)  # pending | sent | failed | gave_up
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(String(300), nullable=True)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    next_try_at = Column(UtcDateTime, nullable=True)
    sent_at = Column(UtcDateTime, nullable=True)

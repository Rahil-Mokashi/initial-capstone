"""Per-payment-mode totals for a shift, typed by the cashier from the attendants' bundle.

The attendants never touch the computer: at shift end they hand over the Card / DTP Card / Phone Pay /
PTM / Other slips and the cashier types ONE total per mode (site visit 2026-10-12). Those totals are
the report's "Shift N transaction details" lines, and the bank reconciliation's expected receipts.

Append-only: re-typing a total VOIDS the previous entry (with a reason and time) and adds a new one, so
the earlier figure is never lost. At most one active entry per (shift, tender).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.database.types import UtcDateTime

from .base import Base


class ShiftTenderEntry(Base):
    __tablename__ = "shift_tender_entries"
    __table_args__ = (CheckConstraint("amount >= 0", name="ck_shift_tender_entries_amount_non_negative"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    shift_id = Column(String(36), ForeignKey("shifts.id"), nullable=False, index=True)
    tender_id = Column(String(36), ForeignKey("tenders.id"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    # A slip / batch / settlement reference the cashier can copy from the card machine or app, if any.
    reference = Column(String(128), nullable=True)
    recorded_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    voided_at = Column(UtcDateTime, nullable=True)
    void_reason = Column(Text, nullable=True)

    shift = relationship("Shift")
    tender = relationship("Tender")
    recorded_by = relationship("User")

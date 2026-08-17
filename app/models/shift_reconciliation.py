import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import relationship
from app.database.types import UtcDateTime

from .base import Base


class ShiftReconciliation(Base):
    """Cash/UPI/card reconciliation for one shift (problemstatement.md
    #20/#21). Expected totals are computed from the shift's own Sale/
    Payment/Expense records (never a manual entry), then compared
    against what was physically declared - one reconciliation per
    shift, never edited once performed, matching the project's
    recompute-don't-overwrite rule for financial records.

    Expense reconciliation is folded in here rather than built as a
    separate mechanism: an approved expense paid during the shift
    reduces the expected cash-in-hand (or UPI/card balance) for
    whichever method it was paid with, so "expected" already reflects
    money that left the till during the shift, not just what came in.

    classification/status mirror FuelReconciliation's graduated
    severity model (never an accusation) - a low-variance reconciliation
    is auto-accepted, a high-variance one needs a manager/owner to
    approve it via approve_shift_reconciliation, the discrepancy
    workflow's "supervisor review -> manager investigation -> owner
    approval" collapsed into a single approval step, matching this
    app's existing size (one approval action, not a multi-stage ticket
    system) rather than inventing a heavier workflow than the rest of
    the app uses.
    """

    __tablename__ = "shift_reconciliations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    shift_id = Column(String(36), ForeignKey("shifts.id"), nullable=False, unique=True, index=True)

    expected_cash = Column(Numeric(12, 2), nullable=False)
    declared_cash = Column(Numeric(12, 2), nullable=False)
    cash_variance = Column(Numeric(12, 2), nullable=False)

    expected_upi = Column(Numeric(12, 2), nullable=False)
    declared_upi = Column(Numeric(12, 2), nullable=False)
    upi_variance = Column(Numeric(12, 2), nullable=False)

    expected_card = Column(Numeric(12, 2), nullable=False)
    declared_card = Column(Numeric(12, 2), nullable=False)
    card_variance = Column(Numeric(12, 2), nullable=False)

    classification = Column(String(32), nullable=False)
    status = Column(String(20), nullable=False)

    performed_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    performed_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    remarks = Column(Text, nullable=True)

    approved_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    approved_at = Column(UtcDateTime, nullable=True)
    approval_remarks = Column(Text, nullable=True)

    shift = relationship("Shift")
    performed_by = relationship("User", foreign_keys=[performed_by_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])

    def __repr__(self) -> str:
        return f"<ShiftReconciliation(shift_id={self.shift_id!r}, classification={self.classification!r})>"

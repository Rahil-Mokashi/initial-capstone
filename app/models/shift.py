import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from .base import Base, EntityMixin


class Shift(EntityMixin, Base):
    """A single shift's open/close lifecycle (problemstatement.md #11).

    One row per (shift_date, shift_label) — there is exactly one "Morning"
    shift on a given date, not a new row each time it's touched. Once
    closed, a shift must not be freely edited; reopen_shift records who
    reopened it and why rather than silently flipping the status back.
    Status values (open/closed) are ShiftStatus in app/core/constants.py,
    stored in EntityMixin's generic status column.

    Full reconciliation (cash/UPI/card/fuel) is deferred until the
    sales/payments/inventory modules exist (Phases 9-15) — this phase
    covers the open/assign-nozzles/close-with-meter-readings workflow.
    """

    __tablename__ = "shifts"
    __table_args__ = (UniqueConstraint("shift_date", "shift_label", name="uq_shift_date_label"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    shift_date = Column(Date, nullable=False, index=True)
    shift_label = Column(String(64), nullable=False)

    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)

    opened_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    closed_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    supervisor_id = Column(String(36), ForeignKey("users.id"), nullable=True)

    notes = Column(Text, nullable=True)

    reopen_reason = Column(Text, nullable=True)
    reopened_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    reopened_at = Column(DateTime, nullable=True)

    opened_by = relationship("User", foreign_keys=[opened_by_id])
    closed_by = relationship("User", foreign_keys=[closed_by_id])
    supervisor = relationship("User", foreign_keys=[supervisor_id])
    reopened_by = relationship("User", foreign_keys=[reopened_by_id])
    nozzle_assignments = relationship("NozzleAssignment", back_populates="shift")

    def __repr__(self) -> str:
        return f"<Shift(date={self.shift_date!r}, label={self.shift_label!r}, status={self.status!r})>"

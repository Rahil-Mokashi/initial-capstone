import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, Date, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.database.types import UtcDateTime

from .base import Base


class LeaveRequest(Base):
    """One employee's leave request (problemstatement.md #2/#9/#10/#29).

    Deliberately scoped narrow, by the user's own explicit choice
    (client-perspective review, 2026-09-23): this tracks that leave was
    requested, for which dates, why, and who approved or rejected it and
    when - the same request+approval shape already used for Expense
    (approve_expense/reject_expense) - and nothing more. There is no
    leave-type policy (casual/sick/earned), no annual entitlement, no
    accrual, and no carry-forward: those are real HR policy specific to
    the client's pump, not something to invent, and the option to add
    them later stays fully open (see LeaveService's module docstring).

    Approving a request marks the corresponding Attendance rows LEAVE
    (AttendanceService.apply_leave_as_related_action) - it does not
    duplicate attendance tracking, it drives the existing one.

    Never edited once decided - PENDING is the only state a decision can
    still be made on. A mistaken approval/rejection is corrected either
    by a new request or by directly correcting the Attendance rows the
    approval already wrote (AttendanceService.correct_attendance), never
    by editing this record after the fact - the same VOID/REVERSE/ADJUST-
    not-DELETE rule every other decision record in this app follows.
    """

    __tablename__ = "leave_requests"

    __table_args__ = (
        CheckConstraint("date_from <= date_to", name="ck_leave_requests_date_range"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    employee_id = Column(String(36), ForeignKey("employees.id"), nullable=False, index=True)

    date_from = Column(Date, nullable=False)
    date_to = Column(Date, nullable=False)
    reason = Column(Text, nullable=False)

    status = Column(String(16), nullable=False)

    requested_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # All three set together, once, by whichever of approve/reject/cancel
    # is the first (and only) decision ever made on this request.
    decided_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    decided_at = Column(UtcDateTime, nullable=True)
    decision_reason = Column(Text, nullable=True)

    employee = relationship("Employee")
    requested_by = relationship("User", foreign_keys=[requested_by_id])
    decided_by = relationship("User", foreign_keys=[decided_by_id])

    def __repr__(self) -> str:
        return f"<LeaveRequest(employee_id={self.employee_id!r}, {self.date_from}..{self.date_to}, status={self.status!r})>"

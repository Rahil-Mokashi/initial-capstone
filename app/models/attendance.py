import uuid

from sqlalchemy import Column, Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database.types import UtcDateTime

from .base import Base, EntityMixin


class Attendance(EntityMixin, Base):
    """Daily attendance record for one employee (problemstatement.md #9).

    One row per employee per date (enforced by a unique constraint) —
    once marked, further changes go through the correction workflow
    (correction_reason/corrected_by_id/corrected_at) rather than a plain
    overwrite, and every correction is also audit-logged with old/new
    values by AttendanceService.

    shift_id links to the real Shift entity (Phase 7), migrated
    2026-09-23 from what used to be a free-text shift_label - Shift
    didn't exist yet when Attendance was first built (Phase 6). shift_id
    is nullable: attendance is routinely marked for a date that has no
    Shift row at all (Shift is opened separately, per shift, and isn't a
    prerequisite for marking who was present). shift_label is kept
    alongside it, never dropped, as the historical free-text record for
    rows the migration could not confidently match to a real Shift.
    """

    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("employee_id", "attendance_date", name="uq_attendance_employee_date"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    employee_id = Column(String(36), ForeignKey("employees.id"), nullable=False, index=True)
    attendance_date = Column(Date, nullable=False, index=True)

    check_in_time = Column(UtcDateTime, nullable=True)
    check_out_time = Column(UtcDateTime, nullable=True)
    shift_label = Column(String(64), nullable=True)
    shift_id = Column(String(36), ForeignKey("shifts.id"), nullable=True, index=True)
    supervisor_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    overtime_minutes = Column(Integer, nullable=False, default=0)

    correction_reason = Column(String(512), nullable=True)
    corrected_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    corrected_at = Column(UtcDateTime, nullable=True)

    employee = relationship("Employee")
    shift = relationship("Shift")
    supervisor = relationship("User", foreign_keys=[supervisor_id])
    corrected_by = relationship("User", foreign_keys=[corrected_by_id])

    def __repr__(self) -> str:
        return f"<Attendance(employee_id={self.employee_id!r}, date={self.attendance_date!r}, status={self.status!r})>"

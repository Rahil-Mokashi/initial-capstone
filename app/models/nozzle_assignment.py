import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, ForeignKey, Numeric, String
from sqlalchemy.orm import relationship
from app.database.types import UtcDateTime

from .base import Base, EntityMixin


class NozzleAssignment(EntityMixin, Base):
    """One attendant's assignment to one nozzle for one shift (problemstatement.md #8).

    Prevention rules (enforced in ShiftService, not here): an employee
    cannot hold two ACTIVE assignments within the same shift, and a
    nozzle cannot have two ACTIVE assignments within the same shift.
    Status values (active/completed/cancelled) are AssignmentStatus in
    app/core/constants.py, stored in EntityMixin's generic status column.
    """

    __tablename__ = "nozzle_assignments"

    # Value invariants enforced by the DATABASE, not just by Python.
    # Foreign keys were already enforced at this level (PRAGMA
    # foreign_keys=ON); the argument for value rules is identical, and
    # the .db file is directly reachable by anyone with the machine.
    __table_args__ = (
        CheckConstraint("opening_meter >= 0", name="ck_nozzle_assignments_opening_meter_non_negative"),
        CheckConstraint("closing_meter IS NULL OR closing_meter >= opening_meter", name="ck_nozzle_assignments_closing_not_before_opening"),
    )


    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    employee_id = Column(String(36), ForeignKey("employees.id"), nullable=False, index=True)
    nozzle_id = Column(String(36), ForeignKey("nozzles.id"), nullable=False, index=True)
    shift_id = Column(String(36), ForeignKey("shifts.id"), nullable=False, index=True)

    start_time = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    end_time = Column(UtcDateTime, nullable=True)

    opening_meter = Column(Numeric(12, 3), nullable=False)
    closing_meter = Column(Numeric(12, 3), nullable=True)

    assigned_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    remarks = Column(String(512), nullable=True)

    employee = relationship("Employee")
    nozzle = relationship("Nozzle")
    shift = relationship("Shift", back_populates="nozzle_assignments")
    assigned_by = relationship("User")

    def __repr__(self) -> str:
        return f"<NozzleAssignment(employee_id={self.employee_id!r}, nozzle_id={self.nozzle_id!r}, status={self.status!r})>"

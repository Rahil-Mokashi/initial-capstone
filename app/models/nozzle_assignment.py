import uuid
from datetime import datetime, timezone
from decimal import Decimal

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
        CheckConstraint("testing_volume >= 0", name="ck_nozzle_assignments_testing_volume_non_negative"),
        CheckConstraint("internal_consumption_volume >= 0", name="ck_nozzle_assignments_internal_consumption_volume_non_negative"),
    )


    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    employee_id = Column(String(36), ForeignKey("employees.id"), nullable=False, index=True)
    nozzle_id = Column(String(36), ForeignKey("nozzles.id"), nullable=False, index=True)
    shift_id = Column(String(36), ForeignKey("shifts.id"), nullable=False, index=True)

    start_time = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    end_time = Column(UtcDateTime, nullable=True)

    opening_meter = Column(Numeric(12, 3), nullable=False)
    closing_meter = Column(Numeric(12, 3), nullable=True)
    # Litres of this assignment's meter difference that were a
    # calibration/dip test rather than a real sale - the fuel is
    # dispensed through this nozzle's meter into a measured can and
    # poured straight back into the tank, so it crosses the meter
    # without ever leaving tank stock. Lives here, not on TankTransaction
    # (see TankTransactionType's docstring), because the meter is where
    # it's actually observed, and it's what SaleService.settle_
    # assignment_cash subtracts before billing the remainder as a cash
    # sale - otherwise a test dispense gets silently sold to nobody.
    testing_volume = Column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    # Litres of this assignment's meter difference that were internal
    # consumption (genset, vehicle, Omni fills) rather than a real sale
    # (PROJECT_CONTEXT.md's A5 working assumption: there is no other
    # metered way to draw fuel from an underground tank, so this volume
    # sits inside the same meter difference testing_volume is carved out
    # of). Unlike testing_volume, this fuel genuinely leaves the tank and
    # is not poured back - that stock effect is recorded separately, on
    # the Expense that represents this same fill
    # (TankTransactionType.INTERNAL_CONSUMPTION via ExpenseService.
    # create_expense). This field's only job is billing accuracy: what
    # SaleService.settle_assignment_cash subtracts alongside
    # testing_volume so the fuel isn't also sold to a customer who
    # doesn't exist. The two are kept as separate columns, not combined
    # into one "non-sale volume" figure, specifically so a wrong A5 only
    # requires zeroing this one field out - see PROJECT_CONTEXT.md.
    internal_consumption_volume = Column(Numeric(12, 3), nullable=False, default=Decimal("0"))

    assigned_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    remarks = Column(String(512), nullable=True)

    employee = relationship("Employee")
    nozzle = relationship("Nozzle")
    shift = relationship("Shift", back_populates="nozzle_assignments")
    assigned_by = relationship("User")

    def __repr__(self) -> str:
        return f"<NozzleAssignment(employee_id={self.employee_id!r}, nozzle_id={self.nozzle_id!r}, status={self.status!r})>"

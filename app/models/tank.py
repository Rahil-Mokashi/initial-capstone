import uuid

from sqlalchemy import CheckConstraint, Column, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import relationship

from .base import Base, EntityMixin


class Tank(EntityMixin, Base):
    """A physical fuel storage tank (problemstatement.md #13).

    Distinct from Fuel (a fuel-type lookup, also referenced by Nozzle):
    a pump can have more than one tank for the same fuel type, and each
    tank tracks its own capacity/stock independently. Status values
    (active/inactive/maintenance) are TankStatus in app/core/constants.py,
    stored in EntityMixin's generic status column.
    """

    __tablename__ = "tanks"

    # Value invariants enforced by the DATABASE, not just by Python.
    # Foreign keys were already enforced at this level (PRAGMA
    # foreign_keys=ON); the argument for value rules is identical, and
    # the .db file is directly reachable by anyone with the machine.
    __table_args__ = (
        CheckConstraint("capacity > 0", name="ck_tanks_capacity_positive"),
        CheckConstraint("current_stock >= 0", name="ck_tanks_stock_non_negative"),
        CheckConstraint("current_stock <= capacity", name="ck_tanks_stock_within_capacity"),
    )


    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(32), unique=True, nullable=False, index=True)
    fuel_id = Column(String(36), ForeignKey("fuels.id"), nullable=False)

    capacity = Column(Numeric(12, 3), nullable=False)
    current_stock = Column(Numeric(12, 3), nullable=False, default=0)
    opening_stock = Column(Numeric(12, 3), nullable=False, default=0)

    calibration_info = Column(Text, nullable=True)

    fuel = relationship("Fuel")

    def __repr__(self) -> str:
        return f"<Tank(code={self.code!r}, status={self.status!r})>"

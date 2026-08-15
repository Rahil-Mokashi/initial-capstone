import uuid

from sqlalchemy import Column, Float, ForeignKey, String, Text
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

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(32), unique=True, nullable=False, index=True)
    fuel_id = Column(String(36), ForeignKey("fuels.id"), nullable=False)

    capacity = Column(Float, nullable=False)
    current_stock = Column(Float, nullable=False, default=0.0)
    opening_stock = Column(Float, nullable=False, default=0.0)

    calibration_info = Column(Text, nullable=True)

    fuel = relationship("Fuel")

    def __repr__(self) -> str:
        return f"<Tank(code={self.code!r}, status={self.status!r})>"

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import relationship

from .base import Base


class TankReading(Base):
    """A dip/stock reading for one tank (problemstatement.md #13).

    Every reading records who took it, when, and the resulting stock
    figure — readings are never edited or deleted once recorded, only
    superseded by a later reading, so the measurement history stays
    intact for reconciliation.
    """

    __tablename__ = "tank_readings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tank_id = Column(String(36), ForeignKey("tanks.id"), nullable=False, index=True)
    employee_id = Column(String(36), ForeignKey("employees.id"), nullable=False)
    shift_id = Column(String(36), ForeignKey("shifts.id"), nullable=True)

    reading_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    dip_value = Column(Numeric(12, 3), nullable=True)
    physical_stock = Column(Numeric(12, 3), nullable=False)
    remarks = Column(Text, nullable=True)

    tank = relationship("Tank")
    employee = relationship("Employee")
    shift = relationship("Shift")

    def __repr__(self) -> str:
        return f"<TankReading(tank_id={self.tank_id!r}, physical_stock={self.physical_stock!r})>"

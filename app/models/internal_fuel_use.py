"""Fuel the pump itself used (own vehicle, genset, Omni): the litres and the vehicle behind an expense line.

The report records it as an EXPENSE at selling price with litres, and does NOT also reduce tank stock:
that fuel already passed through the nozzle meters, so a second deduction would double count (the same
trap as TESTING). Setting `internal_fuel_deducts_tank` (T-12) is off by default. The expense itself is a
normal Expense (approval workflow unchanged); this row only adds the typed detail the report prints.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, ForeignKey, Numeric, String
from sqlalchemy.orm import relationship

from app.database.types import UtcDateTime

from .base import Base


class InternalFuelUse(Base):
    __tablename__ = "internal_fuel_uses"
    __table_args__ = (CheckConstraint("litres > 0", name="ck_internal_fuel_uses_litres_positive"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    expense_id = Column(String(36), ForeignKey("expenses.id"), nullable=False, unique=True)
    fuel_id = Column(String(36), ForeignKey("fuels.id"), nullable=False)
    litres = Column(Numeric(12, 3), nullable=False)
    rate = Column(Numeric(10, 2), nullable=False)
    # Free text the staff already write: a registration number, "Genset", "Omni".
    vehicle = Column(String(64), nullable=False)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    expense = relationship("Expense")
    fuel = relationship("Fuel")

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Column, Numeric, String

from .base import Base, EntityMixin


class Fuel(EntityMixin, Base):
    """A fuel-type lookup (Petrol/Diesel/Power). Stock/capacity live on
    Tank, not here — a pump can have multiple tanks per fuel type, so
    Fuel itself only owns the price; it used to also carry
    capacity/current_stock/opening_stock for the now-removed
    InventoryService stub, which duplicated Tank and was dead code."""

    __tablename__ = "fuels"

    # Value invariants enforced by the DATABASE, not just by Python.
    # Foreign keys were already enforced at this level (PRAGMA
    # foreign_keys=ON); the argument for value rules is identical, and
    # the .db file is directly reachable by anyone with the machine.
    __table_args__ = (
        CheckConstraint("rate_per_liter >= 0", name="ck_fuels_rate_non_negative"),
    )


    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    fuel_type = Column(String(128), nullable=False, index=True)
    rate_per_liter = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    is_active = Column(Boolean, default=True, nullable=False)

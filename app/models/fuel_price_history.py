import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, Column, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import relationship
from app.database.types import UtcDateTime

from .base import Base, EntityMixin


class FuelPriceHistory(EntityMixin, Base):
    """Append-only record of every change to a fuel's selling price.

    Fuel.rate_per_liter is a single mutable cell holding the price right
    now, which is all a new sale needs (Sale snapshots its own rate at
    the moment of sale, per the user's confirmed 2026-08-16 requirement,
    so a completed sale's amount never shifts when the price changes).
    But a single cell cannot answer the questions a manager and an
    auditor actually ask: what was Petrol priced at on the 14th, who
    changed it, and what did our margin look like either side of the
    revision.

    So every price change appends a row here rather than only
    overwriting the cell - the same VOID/REVERSE/ADJUST-not-DELETE rule
    every other financial record in this app follows. Rows are never
    updated or deleted; a correction is another row.
    """

    __tablename__ = "fuel_price_history"

    # Value invariants enforced by the DATABASE, not just by Python.
    # Foreign keys were already enforced at this level (PRAGMA
    # foreign_keys=ON); the argument for value rules is identical, and
    # the .db file is directly reachable by anyone with the machine.
    __table_args__ = (
        CheckConstraint("new_rate_per_liter > 0", name="ck_fuel_price_history_new_rate_positive"),
    )


    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    fuel_id = Column(String(36), ForeignKey("fuels.id"), nullable=False, index=True)

    # Nullable because the very first price a fuel is ever given has no
    # predecessor - the seeded 0.00 placeholder is not a real price
    # anyone set, and recording it as one would be a lie.
    old_rate_per_liter = Column(Numeric(10, 2), nullable=True)
    new_rate_per_liter = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))

    # Reason is mandatory at the service layer, mirroring set_credit_limit
    # and every other consequential change in this app.
    reason = Column(Text, nullable=False)

    changed_by_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    effective_from = Column(UtcDateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    fuel = relationship("Fuel")

    def __repr__(self) -> str:
        return (
            f"<FuelPriceHistory(fuel_id={self.fuel_id!r}, "
            f"{self.old_rate_per_liter} -> {self.new_rate_per_liter})>"
        )

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import relationship

from .base import Base


class FuelReconciliation(Base):
    """One reconciliation record for one tank on one date (problemstatement.md #14).

    Expected Closing Stock = Opening Stock + Received - Sold. Variance is
    physical minus expected, classified (never assumed to be theft) using
    configurable thresholds in app/core/constants.py. Immutable — a
    reconciliation is never edited after the fact; if it needs revisiting,
    a new reconciliation record is created.
    """

    __tablename__ = "fuel_reconciliations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tank_id = Column(String(36), ForeignKey("tanks.id"), nullable=False, index=True)
    reconciliation_date = Column(Date, nullable=False, index=True)

    opening_stock = Column(Numeric(12, 3), nullable=False)
    received_quantity = Column(Numeric(12, 3), nullable=False)
    sold_quantity = Column(Numeric(12, 3), nullable=False)
    expected_closing_stock = Column(Numeric(12, 3), nullable=False)
    physical_stock = Column(Numeric(12, 3), nullable=False)
    variance = Column(Numeric(12, 3), nullable=False)
    variance_percent = Column(Numeric(8, 3), nullable=False)
    classification = Column(String(32), nullable=False)

    performed_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    remarks = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    tank = relationship("Tank")
    performed_by = relationship("User")

    def __repr__(self) -> str:
        return f"<FuelReconciliation(tank_id={self.tank_id!r}, classification={self.classification!r})>"

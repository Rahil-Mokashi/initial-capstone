import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, Column, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import relationship
from app.database.types import UtcDateTime

from .base import Base


class FuelReconciliation(Base):
    """One reconciliation record for one tank on one date (problemstatement.md #14).

    Expected Closing Stock = Opening Stock + Received - Sold - Internal
    Consumption. Both are summed the same way (from TankTransaction rows
    of those types, TankService._perform_reconciliation_impl) rather than
    entered by hand, so they can never silently drift out of sync with
    the transactions that actually back them - the same recompute-from-
    scratch discipline this project already applies to CreditAccount's
    outstanding balance and PurchaseOrder.status.

    testing_quantity is NOT part of that formula, despite the name
    sitting right next to internal_consumption_quantity above - this was
    wrong in an earlier version of this class and is worth recording why
    (see PROJECT_CONTEXT.md's "wrong turn" entry). Calibration/dip
    testing dispenses through a nozzle's meter into a measured can and is
    poured straight back into the same tank - it crosses the meter but
    never actually leaves the tank, so it cannot reduce book stock the
    way a real sale or internal consumption does. A real petrol pump's
    own daily report proves this arithmetically: opening + purchase -
    shift1 - shift2 lands exactly on its own "Total Stock" figure, with
    testing nowhere subtracted. testing_quantity here is purely
    informational (sourced from NozzleAssignment.testing_volume via
    TankService, not from any TankTransaction - there is no TESTING
    transaction type), matching the report's own "Testing" row, which is
    displayed but likewise never subtracted from Total Stock.

    Both quantities default to zero for a tank/period with no such
    draws, which is the common case. Variance is physical minus expected,
    classified (never assumed to be theft) using configurable thresholds
    in app/core/constants.py. Immutable — a reconciliation is never
    edited after the fact; if it needs revisiting, a new reconciliation
    record is created.
    """

    __tablename__ = "fuel_reconciliations"

    __table_args__ = (
        CheckConstraint("testing_quantity >= 0", name="ck_fuel_reconciliations_testing_non_negative"),
        CheckConstraint(
            "internal_consumption_quantity >= 0", name="ck_fuel_reconciliations_internal_consumption_non_negative"
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tank_id = Column(String(36), ForeignKey("tanks.id"), nullable=False, index=True)
    reconciliation_date = Column(Date, nullable=False, index=True)

    opening_stock = Column(Numeric(12, 3), nullable=False)
    received_quantity = Column(Numeric(12, 3), nullable=False)
    sold_quantity = Column(Numeric(12, 3), nullable=False)
    testing_quantity = Column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    internal_consumption_quantity = Column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    expected_closing_stock = Column(Numeric(12, 3), nullable=False)
    physical_stock = Column(Numeric(12, 3), nullable=False)
    variance = Column(Numeric(12, 3), nullable=False)
    variance_percent = Column(Numeric(8, 3), nullable=False)
    classification = Column(String(32), nullable=False)

    performed_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    remarks = Column(Text, nullable=True)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    tank = relationship("Tank")
    performed_by = relationship("User")

    def __repr__(self) -> str:
        return f"<FuelReconciliation(tank_id={self.tank_id!r}, classification={self.classification!r})>"

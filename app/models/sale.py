import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import relationship
from app.database.types import UtcDateTime

from .base import Base


class Sale(Base):
    """One fuel sale (problemstatement.md #16, #17).

    rate_per_liter and amount are a snapshot at the moment of the sale,
    never a live lookup against Fuel.rate_per_liter - fuel prices change
    over time, and a completed sale's amount must never silently shift
    later just because today's price is different (user-confirmed
    requirement, 2026-08-16). fuel_id is snapshotted too, for the same
    reason a nozzle's fuel assignment could in principle change later.

    A completed sale creates a real Tank ISSUE transaction through
    TankService, the same audited path every other stock movement uses.
    Sales are never deleted - cancel_sale/reverse_sale change status and
    post a compensating ADJUSTMENT transaction, matching the project's
    VOID/REVERSE/ADJUST-not-DELETE rule for financial records.
    """

    __tablename__ = "sales"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    receipt_number = Column(String(32), unique=True, nullable=False, index=True)

    sale_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    shift_id = Column(String(36), ForeignKey("shifts.id"), nullable=False, index=True)
    nozzle_id = Column(String(36), ForeignKey("nozzles.id"), nullable=False, index=True)
    fuel_id = Column(String(36), ForeignKey("fuels.id"), nullable=False)
    employee_id = Column(String(36), ForeignKey("employees.id"), nullable=False)

    quantity = Column(Numeric(12, 3), nullable=False)
    rate_per_liter = Column(Numeric(10, 2), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)

    payment_method = Column(String(16), nullable=False)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=True)

    status = Column(String(16), nullable=False)
    cancellation_reason = Column(Text, nullable=True)

    tank_transaction_id = Column(String(36), ForeignKey("tank_transactions.id"), nullable=True)
    reversal_transaction_id = Column(String(36), ForeignKey("tank_transactions.id"), nullable=True)

    recorded_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    remarks = Column(Text, nullable=True)

    shift = relationship("Shift")
    nozzle = relationship("Nozzle")
    fuel = relationship("Fuel")
    employee = relationship("Employee")
    customer = relationship("Customer")
    recorded_by = relationship("User")
    tank_transaction = relationship("TankTransaction", foreign_keys=[tank_transaction_id])
    reversal_transaction = relationship("TankTransaction", foreign_keys=[reversal_transaction_id])

    def __repr__(self) -> str:
        return f"<Sale(receipt_number={self.receipt_number!r}, status={self.status!r})>"

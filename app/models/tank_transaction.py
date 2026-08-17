import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import relationship
from app.database.types import UtcDateTime

from .base import Base


class TankTransaction(Base):
    """An immutable record of stock moving in/out/adjusted for one tank
    (problemstatement.md #13). Receipts and issues will eventually be
    created automatically by Procurement (Phase 10) and Sales (Phase 11);
    for now all three types can be recorded directly. Never edited or
    deleted — a correction is a new adjustment transaction with a reason,
    not a change to history.
    """

    __tablename__ = "tank_transactions"

    # Value invariants enforced by the DATABASE, not just by Python.
    # Foreign keys were already enforced at this level (PRAGMA
    # foreign_keys=ON); the argument for value rules is identical, and
    # the .db file is directly reachable by anyone with the machine.
    __table_args__ = (
        # NOT "quantity > 0". TankTransaction.quantity is a SIGNED stock
        # delta by design (TankService._record_transaction stores ISSUE as
        # negative, RECEIPT as positive, and ADJUSTMENT with whichever sign
        # corrects the tank) - so a positivity constraint would contradict
        # the domain model rather than protect it. What is genuinely
        # meaningless is a movement of nothing.
        CheckConstraint("quantity != 0", name="ck_tank_transactions_quantity_non_zero"),
    )


    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tank_id = Column(String(36), ForeignKey("tanks.id"), nullable=False, index=True)
    transaction_type = Column(String(32), nullable=False)
    quantity = Column(Numeric(12, 3), nullable=False)
    recorded_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    transaction_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    reference = Column(String(256), nullable=True)
    remarks = Column(Text, nullable=True)

    tank = relationship("Tank")
    recorded_by = relationship("User")

    def __repr__(self) -> str:
        return f"<TankTransaction(tank_id={self.tank_id!r}, type={self.transaction_type!r}, quantity={self.quantity!r})>"

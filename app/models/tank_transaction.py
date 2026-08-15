import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import relationship

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

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tank_id = Column(String(36), ForeignKey("tanks.id"), nullable=False, index=True)
    transaction_type = Column(String(32), nullable=False)
    quantity = Column(Float, nullable=False)
    recorded_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    transaction_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    reference = Column(String(256), nullable=True)
    remarks = Column(Text, nullable=True)

    tank = relationship("Tank")
    recorded_by = relationship("User")

    def __repr__(self) -> str:
        return f"<TankTransaction(tank_id={self.tank_id!r}, type={self.transaction_type!r}, quantity={self.quantity!r})>"

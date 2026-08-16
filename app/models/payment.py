import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import relationship

from .base import Base


class Payment(Base):
    """The settlement record for one Sale (problemstatement.md #17).

    Tracked as its own entity, separate from Sale, because a sale's
    fulfilment (fuel dispensed) and its settlement (money actually
    collected) are related but distinct lifecycles: a CASH/UPI/CARD
    payment is normally SUCCESS the moment the sale is recorded, a
    CREDIT sale's payment starts PENDING (settled later via Phase 13's
    customer payments), and any payment can later be found to have
    FAILED, or be REVERSED (sale cancelled) or REFUNDED (money handed
    back) - never deleted or silently overwritten, matching the
    project's VOID/REVERSE/ADJUST-not-DELETE rule for financial records.

    One payment per sale for now (no split-payment requirement in the
    current business rules) - sale_id is unique.
    """

    __tablename__ = "payments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sale_id = Column(String(36), ForeignKey("sales.id"), nullable=False, unique=True, index=True)

    amount = Column(Numeric(12, 2), nullable=False)
    method = Column(String(16), nullable=False)
    reference_number = Column(String(64), nullable=True)
    status = Column(String(16), nullable=False)

    payment_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    shift_id = Column(String(36), ForeignKey("shifts.id"), nullable=False)
    attendant_id = Column(String(36), ForeignKey("employees.id"), nullable=False)
    recorded_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)

    status_reason = Column(Text, nullable=True)

    sale = relationship("Sale")
    shift = relationship("Shift")
    attendant = relationship("Employee")
    recorded_by = relationship("User")

    def __repr__(self) -> str:
        return f"<Payment(sale_id={self.sale_id!r}, method={self.method!r}, status={self.status!r})>"

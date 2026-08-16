import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import relationship

from .base import Base


class CustomerPayment(Base):
    """A payment received from a credit customer (problemstatement.md
    #18). Applied against the customer's overall outstanding balance,
    not allocated to a specific Sale - matching how CreditAccount's
    balance is computed (total credit sales minus total payments).
    Never edited or deleted once recorded, the same append-only rule
    already applied to SupplierPayment - a correction is a new record."""

    __tablename__ = "customer_payments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=False, index=True)

    amount = Column(Numeric(12, 2), nullable=False)
    payment_date = Column(Date, nullable=False)
    payment_method = Column(String(16), nullable=False)
    reference = Column(String(128), nullable=True)

    recorded_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    remarks = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    customer = relationship("Customer")
    recorded_by = relationship("User")

    def __repr__(self) -> str:
        return f"<CustomerPayment(customer_id={self.customer_id!r}, amount={self.amount!r})>"

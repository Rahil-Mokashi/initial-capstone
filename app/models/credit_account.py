import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship
from app.database.types import UtcDateTime

from .base import Base


class CreditAccount(Base):
    """One credit account per Customer (problemstatement.md #18).

    Opting a customer into credit sales is a deliberate step, not
    implicit: a Customer with no CreditAccount cannot be sold to on
    CREDIT (see SaleService.create_sale's credit-limit check). The
    outstanding balance is never stored here - it's always recomputed
    from credit Sales minus CustomerPayments (CreditService.
    get_outstanding_balance), the same "recompute from scratch, never
    let it drift" approach already used for SupplierInvoice.status and
    PurchaseOrder.status, so it can never silently drift out of sync.

    payment_due_days is used only to flag the account as overdue (a
    graduated signal, like fuel reconciliation variance - never an
    accusation) once its oldest unpaid credit sale is older than this
    many days; it is not a per-sale due date, since payments are
    recorded against the account as a whole, not allocated to specific
    sales.
    """

    __tablename__ = "credit_accounts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=False, unique=True, index=True)

    credit_limit = Column(Numeric(12, 2), nullable=False)
    payment_due_days = Column(Integer, nullable=False, default=30)

    created_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        UtcDateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    customer = relationship("Customer")
    created_by = relationship("User")

    def __repr__(self) -> str:
        return f"<CreditAccount(customer_id={self.customer_id!r}, credit_limit={self.credit_limit!r})>"

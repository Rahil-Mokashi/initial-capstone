"""Credit control added after the site visit (2026-10-12): who approved a credit customer, every time the
credit limit was overridden and by whom, the follow-up (chasing) log per customer, and the vehicle/slip
numbers the owners want on a customer's statement (J-05).

Nothing here changes how a credit sale is recorded (Sale, CreditAccount, CustomerPayment are untouched);
these are records beside them. All append-only except a follow-up's outcome, which is closed once.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.database.types import UtcDateTime

from .base import Base


class CustomerApproval(Base):
    """V-10: who let this customer have credit, and when. One row per customer."""

    __tablename__ = "customer_approvals"
    __table_args__ = (CheckConstraint("status IN ('pending','approved','rejected')", name="ck_customer_approvals_status"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=False, unique=True, index=True)
    status = Column(String(12), nullable=False)
    requested_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    requested_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    decided_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    decided_at = Column(UtcDateTime, nullable=True)
    note = Column(Text, nullable=True)
    # W-34: made at the Terminal counter with a limit of 0; the first sale is allowed, the next waits for an owner.
    counter_created = Column(Boolean, nullable=False, default=False, server_default="0")

    customer = relationship("Customer")
    decided_by = relationship("User", foreign_keys=[decided_by_id])


class CreditLimitOverride(Base):
    """A credit sale that went past the customer's limit, with the owner who allowed it (V-14)."""

    __tablename__ = "credit_limit_overrides"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=False, index=True)
    sale_id = Column(String(36), ForeignKey("sales.id"), nullable=True, unique=True)
    amount = Column(Numeric(12, 2), nullable=False)
    outstanding_before = Column(Numeric(14, 2), nullable=False)
    credit_limit = Column(Numeric(12, 2), nullable=False)
    reason = Column(Text, nullable=False)
    approved_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    requested_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    customer = relationship("Customer")
    approved_by = relationship("User", foreign_keys=[approved_by_id])


class CreditFollowUp(Base):
    """One contact with a customer about money owed, and any promise made."""

    __tablename__ = "credit_follow_ups"
    __table_args__ = (
        CheckConstraint("status IN ('open','kept','broken','cancelled')", name="ck_credit_follow_ups_status"),
        CheckConstraint("promised_amount IS NULL OR promised_amount > 0", name="ck_credit_follow_ups_amount_positive"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=False, index=True)
    followed_on = Column(Date, nullable=False)
    by_user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    method = Column(String(16), nullable=False)  # call | visit | message | other
    note = Column(Text, nullable=True)
    promised_date = Column(Date, nullable=True, index=True)
    promised_amount = Column(Numeric(12, 2), nullable=True)
    status = Column(String(12), nullable=False, default="open")
    closed_at = Column(UtcDateTime, nullable=True)
    closed_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    customer = relationship("Customer")
    by_user = relationship("User", foreign_keys=[by_user_id])


class CreditBillDetail(Base):
    """Vehicle and slip numbers for a credit sale (shown on the statement where recorded; J-05)."""

    __tablename__ = "credit_bill_details"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sale_id = Column(String(36), ForeignKey("sales.id"), nullable=False, unique=True)
    vehicle_no = Column(String(32), nullable=True)
    slip_no = Column(String(64), nullable=True)
    updated_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    updated_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

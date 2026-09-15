import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, ForeignKey, Numeric, String
from sqlalchemy.orm import relationship
from app.database.types import UtcDateTime

from .base import Base


class ShiftBankDeposit(Base):
    """One named bank-deposit line on a shift's cash book (docs/daily-
    report-spec.md section 4 - the reference report shows several,
    all "Sopankaka Bank", with different amounts). Many per
    ShiftCashBook, unlike advance_amount/final_amount which are single
    figures - a real shift can deposit into more than one bank, or make
    more than one deposit into the same one.

    Never edited or deleted once recorded - a correction is a new,
    compensating entry, matching this project's VOID/REVERSE/ADJUST-not-
    DELETE rule for financial records. The running total these
    contribute to (ShiftCashBookService's closing cash-in-hand
    derivation) is always recomputed from the actual rows here, never
    stored redundantly.
    """

    __tablename__ = "shift_bank_deposits"

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_shift_bank_deposits_amount_positive"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    shift_cash_book_id = Column(String(36), ForeignKey("shift_cash_books.id"), nullable=False, index=True)

    bank_name = Column(String(255), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)

    recorded_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    recorded_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    shift_cash_book = relationship("ShiftCashBook", back_populates="bank_deposits")
    recorded_by = relationship("User")

    def __repr__(self) -> str:
        return f"<ShiftBankDeposit(bank_name={self.bank_name!r}, amount={self.amount!r})>"

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, Column, ForeignKey, Numeric, String
from sqlalchemy.orm import relationship
from app.database.types import UtcDateTime

from .base import Base


class ShiftCashBook(Base):
    """The office's cash-custody record for one shift (problemstatement.md
    #20/#21, docs/daily-report-spec.md section 4; A1 in PROJECT_CONTEXT.md's
    working assumptions). One row per shift, like ShiftReconciliation -
    but a different concern: ShiftReconciliation compares expected tender
    totals against what was declared (is the till right), while this
    tracks physical cash *custody* moving from the shift till to the
    office (who is holding how much cash, and when it moved).

    advance_amount and final_amount are custody transfers, not expenses
    or payouts - the money moves from the shift till into the office's
    own hands, it never leaves the business (A1). "Advance" is an
    interim handover during the shift (the till would otherwise
    accumulate more cash than is safe/practical to hold at the pump);
    "Final" is the handover at shift close. Both default to 0 - a shift
    that never advances cash mid-shift, or has nothing left to hand over
    at close, is a normal, not a missing, case.

    advance_amount/final_amount plus the related ShiftBankDeposit rows
    (Step 4, one-to-many - a shift can deposit into more than one bank,
    or make more than one deposit) are the only things actually stored.
    Opening balance and closing cash-in-hand are never stored anywhere -
    ShiftCashBookService derives both at read time from this row plus
    the previous shift's own derived closing balance: the same
    "recompute rather than let it drift" discipline this project already
    applies to CreditAccount's outstanding balance and PurchaseOrder.status.
    """

    __tablename__ = "shift_cash_books"

    __table_args__ = (
        CheckConstraint("advance_amount >= 0", name="ck_shift_cash_books_advance_non_negative"),
        CheckConstraint("final_amount >= 0", name="ck_shift_cash_books_final_non_negative"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    shift_id = Column(String(36), ForeignKey("shifts.id"), nullable=False, unique=True, index=True)

    advance_amount = Column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    final_amount = Column(Numeric(12, 2), nullable=False, default=Decimal("0"))

    recorded_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    recorded_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    shift = relationship("Shift")
    recorded_by = relationship("User")
    bank_deposits = relationship(
        "ShiftBankDeposit", back_populates="shift_cash_book", order_by="ShiftBankDeposit.recorded_at"
    )

    def __repr__(self) -> str:
        return f"<ShiftCashBook(shift_id={self.shift_id!r}, advance={self.advance_amount!r}, final={self.final_amount!r})>"

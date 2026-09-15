import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database.types import UtcDateTime

from .base import Base


class EmployeeCashShortage(Base):
    """A cash shortage found at shift reconciliation (docs/daily-report-
    spec.md section 4; A2 in PROJECT_CONTEXT.md's working assumptions),
    booked as an Expense the moment it's found (so the books balance
    immediately - see EmployeeShortageService.record_shortage, which
    creates both rows together) and simultaneously tracked here as a
    receivable against the employee named responsible for it - never
    written off, never silently absorbed.

    Naming which employee is responsible is a deliberate human judgement
    call at the moment of recording, not something derived from the
    reconciliation itself - a shift can have several attendants across
    several nozzle assignments, and reconciliation alone has no notion
    of which one to blame. One shortage per ShiftReconciliationLine (a
    variance can only be booked once), enforced by the unique
    constraint below - `amount` is always sourced from that line's own
    variance, never re-typed.

    Outstanding balance is never stored here - always recomputed as
    amount minus every EmployeeShortageRecovery against it
    (EmployeeShortageService.get_outstanding_balance), the same
    "recompute, don't let it drift" rule this project already applies
    to CreditAccount's outstanding balance.
    """

    __tablename__ = "employee_cash_shortages"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_employee_cash_shortages_amount_positive"),
        UniqueConstraint("shift_reconciliation_line_id", name="uq_employee_cash_shortages_line"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    shift_reconciliation_line_id = Column(
        String(36), ForeignKey("shift_reconciliation_lines.id"), nullable=False,
    )
    employee_id = Column(String(36), ForeignKey("employees.id"), nullable=False, index=True)
    # The Expense booked at the same moment, atomically (see
    # EmployeeShortageService.record_shortage's unit_of_work) - one
    # Expense exists for exactly one shortage, never shared.
    expense_id = Column(String(36), ForeignKey("expenses.id"), nullable=False, unique=True)

    amount = Column(Numeric(12, 2), nullable=False)
    notes = Column(Text, nullable=True)

    recorded_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    recorded_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    shift_reconciliation_line = relationship("ShiftReconciliationLine")
    employee = relationship("Employee")
    expense = relationship("Expense")
    recorded_by = relationship("User")
    recoveries = relationship(
        "EmployeeShortageRecovery", back_populates="shortage", order_by="EmployeeShortageRecovery.recorded_at"
    )

    def __repr__(self) -> str:
        return f"<EmployeeCashShortage(employee_id={self.employee_id!r}, amount={self.amount!r})>"


class EmployeeShortageRecovery(Base):
    """One cash repayment against an EmployeeCashShortage. Partial
    repayments are allowed, the same way CustomerPayment allows a
    partial payment against a CreditAccount balance - the outstanding
    balance is simply whatever's left after summing every recovery (see
    EmployeeCashShortage's own docstring).

    On the pump's own paper report this repayment is a real cash
    receipt into whichever shift's cash book the employee actually
    handed it over during - it shows on the RECEIPT side next to
    Opening Balance/Advance/Final, not as a reversal of the original
    shortage Expense (that Expense already happened and stays booked;
    this is new cash arriving at the counter, possibly during a later
    shift than the one the shortage was found in). shift_cash_book_id
    is therefore required, mirroring ShiftBankDeposit's own shape
    exactly - many recoveries per cash book, summed at read time by
    ShiftCashBookService, never stored redundantly on ShiftCashBook
    itself."""

    __tablename__ = "employee_shortage_recoveries"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_employee_shortage_recoveries_amount_positive"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    employee_cash_shortage_id = Column(
        String(36), ForeignKey("employee_cash_shortages.id"), nullable=False, index=True,
    )
    shift_cash_book_id = Column(String(36), ForeignKey("shift_cash_books.id"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    notes = Column(Text, nullable=True)

    recorded_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    recorded_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    shortage = relationship("EmployeeCashShortage", back_populates="recoveries")
    shift_cash_book = relationship("ShiftCashBook")
    recorded_by = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<EmployeeShortageRecovery(employee_cash_shortage_id={self.employee_cash_shortage_id!r}, "
            f"amount={self.amount!r})>"
        )

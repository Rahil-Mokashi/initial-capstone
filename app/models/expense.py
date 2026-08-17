import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import relationship
from app.database.types import UtcDateTime

from .base import Base, EntityMixin


class ExpenseCategory(EntityMixin, Base):
    """Expense category master data (problemstatement.md #22), same
    simple name+status pattern as Supplier - never deleted, only
    deactivated, since historical expenses must keep referencing it."""

    __tablename__ = "expense_categories"



    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    def __repr__(self) -> str:
        return f"<ExpenseCategory(name={self.name!r}, status={self.status!r})>"


class Expense(Base):
    """One expense record (problemstatement.md #22). Never deleted or
    edited once approved/rejected - a correction is a new expense, the
    same VOID/REVERSE/ADJUST-not-DELETE rule applied to every other
    financial record in this app. status starts PENDING and is only
    ever moved forward by approve_expense/reject_expense, both of which
    require the stricter EXPENSE_APPROVE permission and are audit-logged.
    """

    __tablename__ = "expenses"

    # Value invariants enforced by the DATABASE, not just by Python.
    # Foreign keys were already enforced at this level (PRAGMA
    # foreign_keys=ON); the argument for value rules is identical, and
    # the .db file is directly reachable by anyone with the machine.
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_expenses_amount_positive"),
    )


    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    category_id = Column(String(36), ForeignKey("expense_categories.id"), nullable=False, index=True)

    amount = Column(Numeric(12, 2), nullable=False)
    expense_date = Column(Date, nullable=False)
    payment_method = Column(String(16), nullable=False)
    receipt_reference = Column(String(128), nullable=True)
    description = Column(Text, nullable=True)

    employee_id = Column(String(36), ForeignKey("employees.id"), nullable=False)
    shift_id = Column(String(36), ForeignKey("shifts.id"), nullable=True)

    status = Column(String(16), nullable=False)
    approved_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    approved_at = Column(UtcDateTime, nullable=True)
    approval_remarks = Column(Text, nullable=True)

    recorded_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    category = relationship("ExpenseCategory")
    employee = relationship("Employee")
    shift = relationship("Shift")
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    recorded_by = relationship("User", foreign_keys=[recorded_by_id])

    def __repr__(self) -> str:
        return f"<Expense(category_id={self.category_id!r}, amount={self.amount!r}, status={self.status!r})>"

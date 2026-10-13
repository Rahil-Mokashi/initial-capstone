"""Payroll v1 (site visit 2026-10-12): salaries and advances were kept and tallied in Excel by a separate person; this moves
the tallies into the app so the owners can SEE them verified.

Salary rules are settings, not invented formulas (U-04). The default is the one the brief gives: monthly salary prorated by
days present, deductions typed explicitly. A run is prepared (draft), approved by an OWNER, and only then marked paid, cash or
bank. Nothing is deleted: a wrong advance or payment is voided with a reason.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database.types import UtcDateTime

from .base import Base


class SalarySetup(Base):
    """A monthly salary for an employee from a date. History is kept: the newest one that has started applies."""

    __tablename__ = "salary_setups"
    __table_args__ = (CheckConstraint("monthly_salary > 0", name="ck_salary_setups_positive"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    employee_id = Column(String(36), ForeignKey("employees.id"), nullable=False, index=True)
    monthly_salary = Column(Numeric(12, 2), nullable=False)
    effective_from = Column(Date, nullable=False)
    note = Column(Text, nullable=True)
    set_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    employee = relationship("Employee")


class EmployeeAdvance(Base):
    __tablename__ = "employee_advances"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_employee_advances_positive"),
        CheckConstraint("status IN ('active','void')", name="ck_employee_advances_status"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    employee_id = Column(String(36), ForeignKey("employees.id"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    given_on = Column(Date, nullable=False)
    method = Column(String(8), nullable=False, default="cash")
    note = Column(Text, nullable=True)
    given_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    status = Column(String(8), nullable=False, default="active")
    void_reason = Column(Text, nullable=True)
    voided_at = Column(UtcDateTime, nullable=True)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    employee = relationship("Employee")


class PayrollRun(Base):
    __tablename__ = "payroll_runs"
    __table_args__ = (CheckConstraint("status IN ('draft','approved','paid')", name="ck_payroll_runs_status"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    month = Column(String(7), nullable=False, unique=True)  # 2026-10
    status = Column(String(10), nullable=False, default="draft")
    days_in_month = Column(Integer, nullable=False)
    leave_paid = Column(String(3), nullable=False, default="off")  # rules as they were when the month was prepared
    holiday_paid = Column(String(3), nullable=False, default="off")
    prepared_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    prepared_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    approved_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    approved_at = Column(UtcDateTime, nullable=True)
    paid_at = Column(UtcDateTime, nullable=True)

    lines = relationship("PayrollLine", back_populates="run", order_by="PayrollLine.employee_name")
    approved_by = relationship("User", foreign_keys=[approved_by_id])


class PayrollLine(Base):
    __tablename__ = "payroll_lines"
    __table_args__ = (
        UniqueConstraint("run_id", "employee_id", name="uq_payroll_lines_run_employee"),
        CheckConstraint("advance_deduction >= 0 AND shortage_deduction >= 0 AND other_deduction >= 0", name="ck_payroll_lines_deductions"),
        CheckConstraint("net = gross - advance_deduction - shortage_deduction - other_deduction", name="ck_payroll_lines_net"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String(36), ForeignKey("payroll_runs.id"), nullable=False, index=True)
    employee_id = Column(String(36), ForeignKey("employees.id"), nullable=False, index=True)
    employee_name = Column(String(255), nullable=False)
    monthly_salary = Column(Numeric(12, 2), nullable=False)
    days_in_month = Column(Integer, nullable=False)
    days_present = Column(Numeric(5, 1), nullable=False)
    paid_days = Column(Numeric(5, 1), nullable=False)
    gross = Column(Numeric(12, 2), nullable=False)
    advance_deduction = Column(Numeric(12, 2), nullable=False, default=0)
    shortage_deduction = Column(Numeric(12, 2), nullable=False, default=0)
    other_deduction = Column(Numeric(12, 2), nullable=False, default=0)
    other_note = Column(String(255), nullable=True)
    net = Column(Numeric(12, 2), nullable=False)

    run = relationship("PayrollRun", back_populates="lines")
    employee = relationship("Employee")


class PayrollPayment(Base):
    __tablename__ = "payroll_payments"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_payroll_payments_amount"),
        CheckConstraint("method IN ('cash','bank')", name="ck_payroll_payments_method"),
        CheckConstraint("status IN ('active','void')", name="ck_payroll_payments_status"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    line_id = Column(String(36), ForeignKey("payroll_lines.id"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    method = Column(String(8), nullable=False)
    bank_account_id = Column(String(36), ForeignKey("bank_accounts.id"), nullable=True)  # when paid from the bank
    paid_on = Column(Date, nullable=False)
    reference = Column(String(128), nullable=True)
    paid_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    status = Column(String(8), nullable=False, default="active")
    void_reason = Column(Text, nullable=True)
    voided_at = Column(UtcDateTime, nullable=True)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    line = relationship("PayrollLine")

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator


class EmployeeCashShortageRecord(BaseModel):
    """amount is deliberately absent - EmployeeShortageService.
    record_shortage always sources it from the reconciliation line's own
    variance (A4's "computed, not re-typed" rule), never from user
    input."""

    shift_reconciliation_line_id: str
    employee_id: str
    notes: Optional[str] = None


class EmployeeShortageRecoveryRecord(BaseModel):
    """shift_id names the shift whose cash book physically receives this
    repayment - not necessarily the shift the shortage was found in; an
    employee may repay during a later shift. EmployeeShortageService.
    record_recovery resolves it to that shift's ShiftCashBook and posts
    the receipt there in the same transaction as the recovery row."""

    employee_cash_shortage_id: str
    shift_id: str
    amount: Decimal
    notes: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("amount must be greater than zero")
        return value

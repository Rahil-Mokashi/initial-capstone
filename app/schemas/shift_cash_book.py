from decimal import Decimal

from pydantic import BaseModel, field_validator


class ShiftCashBookRecord(BaseModel):
    shift_id: str
    advance_amount: Decimal = Decimal("0")
    final_amount: Decimal = Decimal("0")

    @field_validator("advance_amount", "final_amount")
    @classmethod
    def non_negative(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("advance_amount and final_amount cannot be negative")
        return value


class ShiftBankDepositRecord(BaseModel):
    shift_id: str
    bank_name: str
    amount: Decimal

    @field_validator("bank_name")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("bank_name must not be blank")
        return value.strip()

    @field_validator("amount")
    @classmethod
    def positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("amount must be greater than zero")
        return value

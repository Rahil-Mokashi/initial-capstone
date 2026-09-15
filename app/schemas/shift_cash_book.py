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

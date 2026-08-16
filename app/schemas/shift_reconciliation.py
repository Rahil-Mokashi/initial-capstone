from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator


class ShiftReconciliationPerform(BaseModel):
    shift_id: str
    declared_cash: Decimal
    declared_upi: Decimal
    declared_card: Decimal
    remarks: Optional[str] = None

    @field_validator("declared_cash", "declared_upi", "declared_card")
    @classmethod
    def non_negative(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("declared amounts cannot be negative")
        return value

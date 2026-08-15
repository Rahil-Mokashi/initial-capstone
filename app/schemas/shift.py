from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator


class ShiftOpen(BaseModel):
    shift_date: date
    shift_label: str
    supervisor_id: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("shift_label")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("shift_label must not be blank")
        return value.strip()


class NozzleAssignmentCreate(BaseModel):
    employee_id: str
    nozzle_id: str
    opening_meter: Decimal
    remarks: Optional[str] = None

    @field_validator("opening_meter")
    @classmethod
    def non_negative(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("opening_meter cannot be negative")
        return value


class NozzleAssignmentComplete(BaseModel):
    closing_meter: Decimal

    @field_validator("closing_meter")
    @classmethod
    def non_negative(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("closing_meter cannot be negative")
        return value

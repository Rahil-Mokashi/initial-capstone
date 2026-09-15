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
    # Litres of the meter difference that were a calibration/dip test,
    # poured back into the tank rather than sold - see NozzleAssignment.
    # testing_volume. Whether this can exceed the actual meter difference
    # depends on opening_meter, which isn't known to this schema; that
    # cross-field check lives in ShiftService.complete_nozzle_assignment.
    testing_volume: Decimal = Decimal("0")

    @field_validator("closing_meter")
    @classmethod
    def non_negative(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("closing_meter cannot be negative")
        return value

    @field_validator("testing_volume")
    @classmethod
    def non_negative_testing_volume(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("testing_volume cannot be negative")
        return value

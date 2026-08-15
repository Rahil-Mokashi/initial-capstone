from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator

from app.core.constants import AttendanceStatus


class AttendanceMark(BaseModel):
    employee_id: str
    attendance_date: date
    status: AttendanceStatus
    check_in_time: Optional[datetime] = None
    check_out_time: Optional[datetime] = None
    shift_label: Optional[str] = None
    supervisor_id: Optional[str] = None
    overtime_minutes: int = 0

    @field_validator("overtime_minutes")
    @classmethod
    def non_negative_overtime(cls, value: int) -> int:
        if value < 0:
            raise ValueError("overtime_minutes cannot be negative")
        return value

    @model_validator(mode="after")
    def check_out_after_check_in(self):
        if self.check_in_time and self.check_out_time and self.check_out_time < self.check_in_time:
            raise ValueError("check_out_time cannot be before check_in_time")
        return self


class AttendanceCorrection(BaseModel):
    status: Optional[AttendanceStatus] = None
    check_in_time: Optional[datetime] = None
    check_out_time: Optional[datetime] = None
    overtime_minutes: Optional[int] = None

    @field_validator("overtime_minutes")
    @classmethod
    def non_negative_overtime(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value < 0:
            raise ValueError("overtime_minutes cannot be negative")
        return value

    @model_validator(mode="after")
    def check_out_after_check_in(self):
        if self.check_in_time and self.check_out_time and self.check_out_time < self.check_in_time:
            raise ValueError("check_out_time cannot be before check_in_time")
        return self

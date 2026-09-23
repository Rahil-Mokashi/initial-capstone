from datetime import date

from pydantic import BaseModel, field_validator, model_validator


class LeaveRequestCreate(BaseModel):
    employee_id: str
    date_from: date
    date_to: date
    reason: str

    @field_validator("reason")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def date_range_is_ordered(self) -> "LeaveRequestCreate":
        if self.date_from > self.date_to:
            raise ValueError("date_from must not be after date_to")
        return self

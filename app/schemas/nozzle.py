from typing import Optional

from pydantic import BaseModel, field_validator


class DispenserCreate(BaseModel):
    code: str

    @field_validator("code")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("code must not be blank")
        return value.strip()


class NozzleCreate(BaseModel):
    code: str
    dispenser_id: str
    fuel_id: str
    tank_id: Optional[str] = None

    @field_validator("code")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("code must not be blank")
        return value.strip()

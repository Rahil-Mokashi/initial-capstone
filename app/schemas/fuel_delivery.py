from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator


class FuelDeliveryArrive(BaseModel):
    purchase_order_id: str
    tank_id: str
    received_by_employee_id: str
    tanker_number: str
    driver_name: Optional[str] = None
    remarks: Optional[str] = None

    @field_validator("tanker_number")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("tanker_number must not be blank")
        return value.strip()


class FuelDeliveryDipReading(BaseModel):
    dip_value: Decimal

    @field_validator("dip_value")
    @classmethod
    def non_negative(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("dip_value cannot be negative")
        return value

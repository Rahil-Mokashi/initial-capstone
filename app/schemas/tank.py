from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, field_validator


class TankCreate(BaseModel):
    code: str
    fuel_id: str
    capacity: float
    opening_stock: float = 0.0
    calibration_info: Optional[str] = None

    @field_validator("code")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("code must not be blank")
        return value.strip()

    @field_validator("capacity")
    @classmethod
    def positive_capacity(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("capacity must be greater than zero")
        return value

    @field_validator("opening_stock")
    @classmethod
    def non_negative_opening_stock(cls, value: float) -> float:
        if value < 0:
            raise ValueError("opening_stock cannot be negative")
        return value


class TankReadingCreate(BaseModel):
    employee_id: str
    physical_stock: float
    dip_value: Optional[float] = None
    shift_id: Optional[str] = None
    remarks: Optional[str] = None
    reading_at: Optional[datetime] = None

    @field_validator("physical_stock")
    @classmethod
    def non_negative_stock(cls, value: float) -> float:
        if value < 0:
            raise ValueError("physical_stock cannot be negative")
        return value


class TankTransactionCreate(BaseModel):
    """quantity's sign convention depends on transaction_type: RECEIPT/ISSUE
    must be positive (the service applies the direction), ADJUSTMENT may be
    positive or negative but not zero — validated in TankService since it
    depends on the type, which isn't part of this schema."""

    quantity: float
    reference: Optional[str] = None
    remarks: Optional[str] = None

    @field_validator("quantity")
    @classmethod
    def non_zero_quantity(cls, value: float) -> float:
        if value == 0:
            raise ValueError("quantity must not be zero")
        return value


class ReconciliationPerform(BaseModel):
    reconciliation_date: date
    physical_stock: float
    remarks: Optional[str] = None

    @field_validator("physical_stock")
    @classmethod
    def non_negative_stock(cls, value: float) -> float:
        if value < 0:
            raise ValueError("physical_stock cannot be negative")
        return value

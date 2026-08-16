from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, field_validator


class PurchaseOrderItemCreate(BaseModel):
    fuel_id: str
    quantity_ordered: Decimal
    rate_per_liter: Decimal

    @field_validator("quantity_ordered")
    @classmethod
    def positive_quantity(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("quantity_ordered must be greater than zero")
        return value

    @field_validator("rate_per_liter")
    @classmethod
    def positive_rate(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("rate_per_liter must be greater than zero")
        return value


class PurchaseOrderCreate(BaseModel):
    supplier_id: str
    expected_delivery_date: Optional[date] = None
    remarks: Optional[str] = None
    items: List[PurchaseOrderItemCreate]

    @field_validator("items")
    @classmethod
    def not_empty(cls, value: List[PurchaseOrderItemCreate]) -> List[PurchaseOrderItemCreate]:
        if not value:
            raise ValueError("A purchase order must have at least one item")
        return value

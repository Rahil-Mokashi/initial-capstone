from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator

from app.core.constants import PaymentMethod


class SaleCreate(BaseModel):
    """rate_per_liter and amount are deliberately not accepted here - the
    service snapshots the fuel's current rate at the moment of sale and
    computes the amount itself, so a sale can never be entered against a
    price the person recording it just made up."""

    shift_id: str
    nozzle_id: str
    employee_id: str
    quantity: Decimal
    payment_method: PaymentMethod
    customer_id: Optional[str] = None
    reference_number: Optional[str] = None
    remarks: Optional[str] = None

    @field_validator("quantity")
    @classmethod
    def positive_quantity(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("quantity must be greater than zero")
        return value

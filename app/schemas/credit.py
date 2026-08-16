from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator

from app.core.constants import PaymentMethod


class CreditAccountCreate(BaseModel):
    customer_id: str
    credit_limit: Decimal
    payment_due_days: int = 30

    @field_validator("credit_limit")
    @classmethod
    def positive_limit(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("credit_limit must be greater than zero")
        return value

    @field_validator("payment_due_days")
    @classmethod
    def positive_due_days(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("payment_due_days must be greater than zero")
        return value


class CustomerPaymentCreate(BaseModel):
    customer_id: str
    amount: Decimal
    payment_method: PaymentMethod
    reference: Optional[str] = None
    remarks: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def positive_amount(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("amount must be greater than zero")
        return value

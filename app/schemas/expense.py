from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator

from app.core.constants import PaymentMethod


class ExpenseCategoryCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()


class ExpenseCreate(BaseModel):
    category_id: str
    amount: Decimal
    payment_method: PaymentMethod
    employee_id: str
    shift_id: Optional[str] = None
    receipt_reference: Optional[str] = None
    description: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def positive_amount(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("amount must be greater than zero")
        return value

    @field_validator("payment_method")
    @classmethod
    def no_credit_expenses(cls, value: PaymentMethod) -> PaymentMethod:
        if value == PaymentMethod.CREDIT:
            raise ValueError("An expense cannot be paid on credit")
        return value

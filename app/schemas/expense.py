from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator

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
    # Set together, only when this expense is really fuel drawn from a
    # tank for internal use (a vehicle, a generator) rather than an
    # ordinary cash expense - see ExpenseService.create_expense and the
    # Expense model's own check constraint enforcing "both or neither".
    tank_id: Optional[str] = None
    quantity: Optional[Decimal] = None

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

    @field_validator("quantity")
    @classmethod
    def positive_quantity(cls, value: Optional[Decimal]) -> Optional[Decimal]:
        if value is not None and value <= 0:
            raise ValueError("quantity must be greater than zero")
        return value

    @model_validator(mode="after")
    def tank_id_and_quantity_together(self) -> "ExpenseCreate":
        if (self.tank_id is None) != (self.quantity is None):
            raise ValueError("tank_id and quantity must be set together, or not at all")
        return self

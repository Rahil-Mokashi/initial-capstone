from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator


class SupplierInvoiceCreate(BaseModel):
    invoice_number: str
    supplier_id: str
    purchase_order_id: Optional[str] = None
    invoice_date: date
    due_date: Optional[date] = None
    amount: Decimal
    remarks: Optional[str] = None

    @field_validator("invoice_number")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("invoice_number must not be blank")
        return value.strip()

    @field_validator("amount")
    @classmethod
    def positive_amount(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("amount must be greater than zero")
        return value


class SupplierPaymentCreate(BaseModel):
    amount: Decimal
    payment_date: date
    payment_method: str
    reference: Optional[str] = None
    remarks: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def positive_amount(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("amount must be greater than zero")
        return value

    @field_validator("payment_method")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("payment_method must not be blank")
        return value.strip()

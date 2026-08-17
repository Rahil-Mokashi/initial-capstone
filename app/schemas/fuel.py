"""Validation schemas for fuel master data and price changes."""

from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

# A sanity ceiling, not a business rule: it exists so a mistyped rate
# (a stray extra digit, or paise entered as rupees) is caught at the
# boundary rather than silently repricing every future sale.
MAX_REASONABLE_RATE_PER_LITER = Decimal("10000")


class FuelRateChange(BaseModel):
    """A new selling price for one fuel, with the reason it changed."""

    new_rate_per_liter: Decimal = Field(gt=0, le=MAX_REASONABLE_RATE_PER_LITER)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("A reason is required to change a fuel price")
        return cleaned


class FuelCreate(BaseModel):
    fuel_type: str = Field(min_length=1, max_length=128)
    rate_per_liter: Decimal = Field(default=Decimal("0"), ge=0, le=MAX_REASONABLE_RATE_PER_LITER)

    @field_validator("fuel_type")
    @classmethod
    def strip_fuel_type(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Fuel type is required")
        return cleaned

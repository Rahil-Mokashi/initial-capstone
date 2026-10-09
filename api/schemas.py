"""Request/response models.

Decimals cross the wire as STRINGS at the backend's scale (money 2 dp,
volume 3 dp - app/core/money.py), never as JSON numbers, so the front end
cannot lose precision. Requests must also send strings and may not carry
more places than the database column stores, so nothing is rounded silently.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer, WithJsonSchema

from app.core.constants import TankStatus, TankTransactionType
from app.core.money import money, volume


def _strings_only(value):
    if isinstance(value, (str, Decimal)):
        return value
    raise ValueError('send numbers as strings, for example "12.500"')


# --- responses -------------------------------------------------------------
MoneyOut = Annotated[Decimal, PlainSerializer(lambda v: str(money(v)), return_type=str, when_used="json")]
VolumeOut = Annotated[Decimal, PlainSerializer(lambda v: str(volume(v)), return_type=str, when_used="json")]
# A percentage shown with two places; same half-up rule as money.
PercentOut = Annotated[Decimal, PlainSerializer(lambda v: str(money(v)), return_type=str, when_used="json")]

# --- requests: Numeric(12, 3) is the widest column these feed ---------------
VolumeIn = Annotated[
    Decimal,
    BeforeValidator(_strings_only),
    Field(max_digits=12, decimal_places=3, allow_inf_nan=False),
    # The generated TypeScript type must say "string" - numbers are rejected.
    WithJsonSchema({"type": "string", "pattern": r"^-?\d{1,9}(\.\d{1,3})?$", "examples": ["12.500"]}),
]


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- auth -------------------------------------------------------------------
class LoginIn(In):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class UserOut(Out):
    id: str
    username: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[str] = None
    permissions: list[str]
    must_change_password: bool


class LoginOut(Out):
    token: str
    expires_at: str
    user: UserOut


class ChangePasswordIn(In):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1)


# --- lookups ----------------------------------------------------------------
class FuelOut(Out):
    id: str
    fuel_type: str


class EmployeeOut(Out):
    id: str
    employee_code: str
    first_name: str
    last_name: str


# --- tanks ------------------------------------------------------------------
class TankOut(Out):
    id: str
    code: str
    fuel_id: str
    fuel_type: str
    status: str
    capacity: VolumeOut
    current_stock: VolumeOut
    opening_stock: VolumeOut
    calibration_info: Optional[str] = None
    fill_percent: PercentOut
    is_low: bool


class TransactionOut(Out):
    id: str
    tank_id: str
    tank_code: str
    transaction_type: str
    quantity: VolumeOut
    transaction_at: datetime
    reference: Optional[str] = None
    remarks: Optional[str] = None
    recorded_by: str


class ReadingOut(Out):
    id: str
    tank_id: str
    reading_at: datetime
    physical_stock: VolumeOut
    dip_value: Optional[VolumeOut] = None
    employee_id: str
    employee_name: str
    remarks: Optional[str] = None


class ReconciliationOut(Out):
    id: str
    tank_id: str
    reconciliation_date: date
    opening_stock: VolumeOut
    received_quantity: VolumeOut
    sold_quantity: VolumeOut
    testing_quantity: VolumeOut
    internal_consumption_quantity: VolumeOut
    expected_closing_stock: VolumeOut
    physical_stock: VolumeOut
    variance: VolumeOut
    variance_percent: PercentOut
    classification: str
    remarks: Optional[str] = None


class TankCreateIn(In):
    code: str
    fuel_id: str
    capacity: VolumeIn
    opening_stock: VolumeIn = Decimal("0")
    calibration_info: Optional[str] = None


class TankStatusIn(In):
    status: TankStatus
    reason: str


class ReadingIn(In):
    employee_id: str
    physical_stock: VolumeIn
    dip_value: Optional[VolumeIn] = None
    remarks: Optional[str] = None


# The Qt screen offers exactly these three; the other types are written by
# other modules (sales, internal consumption) and are not user-entered here.
class TransactionIn(In):
    transaction_type: Literal["receipt", "issue", "adjustment"]
    quantity: VolumeIn
    reference: Optional[str] = None
    remarks: Optional[str] = None

    def type_enum(self) -> TankTransactionType:
        return TankTransactionType(self.transaction_type)


class ReconcileIn(In):
    reconciliation_date: date
    physical_stock: VolumeIn
    remarks: Optional[str] = None

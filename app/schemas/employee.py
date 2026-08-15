import re
from datetime import date
from typing import Optional

from pydantic import BaseModel, field_validator

CONTACT_NUMBER_PATTERN = re.compile(r"^[0-9+\-\s]{7,20}$")


class EmployeeCreate(BaseModel):
    first_name: str
    last_name: str
    contact_number: str
    joining_date: date
    email: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    assigned_outlet: Optional[str] = "Main Outlet"
    role_id: Optional[str] = None
    user_id: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    @field_validator("first_name", "last_name")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()

    @field_validator("contact_number", "emergency_contact_phone")
    @classmethod
    def valid_phone(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if not CONTACT_NUMBER_PATTERN.match(value):
            raise ValueError("must be a valid phone number (digits, spaces, +, - only, 7-20 chars)")
        return value


class EmployeeUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    contact_number: Optional[str] = None
    email: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    assigned_outlet: Optional[str] = None
    role_id: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    @field_validator("contact_number", "emergency_contact_phone")
    @classmethod
    def valid_phone(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if not CONTACT_NUMBER_PATTERN.match(value):
            raise ValueError("must be a valid phone number (digits, spaces, +, - only, 7-20 chars)")
        return value

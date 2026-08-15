import re
from typing import Optional

from pydantic import BaseModel, field_validator

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9._-]{3,64}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    role_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    @field_validator("username")
    @classmethod
    def valid_username(cls, value: str) -> str:
        if not USERNAME_PATTERN.match(value.strip()):
            raise ValueError("username must be 3-64 characters: letters, numbers, dot, underscore, or hyphen")
        return value.strip()

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        if not EMAIL_PATTERN.match(value.strip()):
            raise ValueError("must be a valid email address")
        return value.strip()

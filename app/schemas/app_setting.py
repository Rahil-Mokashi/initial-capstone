"""Validation for the company profile.

Every field is optional: a pump that has not filled in its GST number yet
must still be able to save its name, and blocking the whole form on one
missing field is how settings screens end up never being filled in at all.
What IS validated is the shape of anything actually entered.
"""

from typing import Optional

from pydantic import BaseModel, Field, field_validator

# 15 characters: 2 state code + 10 PAN + 1 entity + 1 'Z' + 1 checksum.
GST_NUMBER_LENGTH = 15


class AppSettingUpdate(BaseModel):
    company_name: Optional[str] = Field(default=None, max_length=200)
    address_line1: Optional[str] = Field(default=None, max_length=200)
    address_line2: Optional[str] = Field(default=None, max_length=200)
    city: Optional[str] = Field(default=None, max_length=100)
    state: Optional[str] = Field(default=None, max_length=100)
    postal_code: Optional[str] = Field(default=None, max_length=20)
    phone: Optional[str] = Field(default=None, max_length=40)
    email: Optional[str] = Field(default=None, max_length=120)
    gst_number: Optional[str] = Field(default=None, max_length=32)
    licence_number: Optional[str] = Field(default=None, max_length=64)
    receipt_footer: Optional[str] = Field(default=None, max_length=500)
    offsite_backup_dir: Optional[str] = Field(default=None, max_length=500)

    @field_validator("*", mode="before")
    @classmethod
    def blank_becomes_none(cls, value):
        """A cleared text box means "not set", not an empty string - so a
        blank field and a never-filled field behave identically."""
        if isinstance(value, str) and not value.strip():
            return None
        return value.strip() if isinstance(value, str) else value

    @field_validator("gst_number")
    @classmethod
    def gst_number_looks_like_one(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.upper()
        if len(cleaned) != GST_NUMBER_LENGTH or not cleaned.isalnum():
            raise ValueError(
                f"A GST number is {GST_NUMBER_LENGTH} alphanumeric characters "
                f"(for example 27AAPFU0939F1ZV)")
        return cleaned

    @field_validator("phone")
    @classmethod
    def phone_is_dialable(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        digits = [c for c in value if c.isdigit()]
        if len(digits) < 6:
            raise ValueError("That does not look like a phone number")
        return value

    @field_validator("email")
    @classmethod
    def email_looks_like_one(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        # Deliberately a shape check, not RFC 5322 - the goal is catching a
        # typo, not certifying deliverability. It does need a non-empty
        # local part though: "@x.com" passed an earlier version of this,
        # because splitting on "@" and checking only the domain half
        # ignores whether anything precedes it.
        local, _, domain = value.partition("@")
        if not local or not domain or "." not in domain or domain.startswith("."):
            raise ValueError("That does not look like an email address")
        return value

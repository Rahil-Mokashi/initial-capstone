import hashlib
import secrets
from typing import List, Tuple

from app.core.constants import (
    PASSWORD_MIN_LENGTH,
    PASSWORD_REQUIRE_DIGIT,
    PASSWORD_REQUIRE_LOWER,
    PASSWORD_REQUIRE_UPPER,
)


def validate_password_strength(password: str) -> List[str]:
    """Validate a password against the configured policy.

    Returns a list of violation messages; an empty list means the password is valid.
    """
    errors = []
    if len(password) < PASSWORD_MIN_LENGTH:
        errors.append(f"Password must be at least {PASSWORD_MIN_LENGTH} characters long")
    if PASSWORD_REQUIRE_UPPER and not any(c.isupper() for c in password):
        errors.append("Password must contain at least one uppercase letter")
    if PASSWORD_REQUIRE_LOWER and not any(c.islower() for c in password):
        errors.append("Password must contain at least one lowercase letter")
    if PASSWORD_REQUIRE_DIGIT and not any(c.isdigit() for c in password):
        errors.append("Password must contain at least one digit")
    return errors


def hash_password(password: str) -> str:
    """Hash a password with a random salt."""
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
    return f"{salt}${pwd_hash.hex()}"


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a password against the stored hash."""
    try:
        salt, stored_hash = hashed_password.split("$", 1)
    except ValueError:
        return False
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
    return secrets.compare_digest(pwd_hash.hex(), stored_hash)


def generate_token() -> str:
    """Generate a random session token."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Deterministically hash a session token for storage/lookup.

    Session tokens are already high-entropy random values (from
    generate_token), so a fast SHA-256 digest is sufficient here — unlike
    passwords, they don't need a slow, salted KDF.
    """
    return hashlib.sha256(token.encode()).hexdigest()

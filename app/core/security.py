import hashlib
import secrets
import string
from typing import List

from app.core.constants import (
    PASSWORD_MIN_LENGTH,
    PASSWORD_REQUIRE_DIGIT,
    PASSWORD_REQUIRE_LOWER,
    PASSWORD_REQUIRE_UPPER,
    PIN_LENGTH,
)

# The weakest possible PINs at PIN_LENGTH digits - every digit repeated,
# and the two obvious sequences - rejected outright rather than merely
# discouraged. A PIN's whole security model is "there are only 10^N
# combinations, so an attacker must be locked out after a few guesses"
# (see MAX_FAILED_LOGIN_ATTEMPTS), and these specific values are the
# first ones anyone - staff choosing their own, or someone guessing at
# it - would try first, so they are worth ruling out even though the
# lockout already covers the rest of the space.
_WEAK_PINS = {
    str(digit) * PIN_LENGTH for digit in range(10)
} | {
    "".join(str(d % 10) for d in range(start, start + PIN_LENGTH))
    for start in range(10)
} | {
    "".join(str(d % 10) for d in range(start, start - PIN_LENGTH, -1))
    for start in range(10)
}


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


def validate_pin_strength(pin: str) -> List[str]:
    """Validate a quick-sign-in PIN against the configured policy.

    Returns a list of violation messages; an empty list means the PIN is
    valid. Deliberately simpler than validate_password_strength - a PIN
    has no upper/lower/digit-mix policy to check (it's digits-only by
    definition), just length and the specific weak values in _WEAK_PINS.
    """
    errors = []
    if len(pin) != PIN_LENGTH or not pin.isdigit():
        errors.append(f"PIN must be exactly {PIN_LENGTH} digits")
        return errors  # further checks assume a well-formed PIN
    if pin in _WEAK_PINS:
        errors.append("That PIN is too easy to guess (repeated or sequential digits). Please choose another.")
    return errors


def generate_numeric_code(length: int) -> str:
    """A random numeric code (e.g. a password-reset code) using a
    cryptographically secure source, not the `random` module - the same
    reasoning generate_token() already applies to session tokens."""
    return "".join(secrets.choice(string.digits) for _ in range(length))


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

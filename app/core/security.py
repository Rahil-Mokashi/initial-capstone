import hashlib
import secrets
from typing import Tuple


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

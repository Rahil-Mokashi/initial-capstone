import uuid
from sqlalchemy import Column, String, Boolean, ForeignKey, Integer
from sqlalchemy.orm import relationship
from app.database.types import UtcDateTime
from .base import Base, EntityMixin


class User(EntityMixin, Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(128), unique=True, nullable=False, index=True)
    email = Column(String(256), unique=True, nullable=False, index=True)
    password_hash = Column(String(512), nullable=False)
    first_name = Column(String(128), nullable=True)
    last_name = Column(String(128), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_locked = Column(Boolean, default=False, nullable=False)
    # When the automatic lockout was applied, so it can expire on its own.
    # Nullable because an account locked by an administrator (rather than
    # by failed attempts) has no expiry and must be cleared deliberately.
    locked_at = Column(UtcDateTime, nullable=True)
    failed_attempts = Column(Integer, default=0, nullable=False)
    must_change_password = Column(Boolean, default=False, nullable=False)
    last_login = Column(UtcDateTime, nullable=True)
    # Optional quick-sign-in PIN, self-service (UserService.set_own_pin) -
    # nullable because most accounts never set one; NULL means "PIN
    # sign-in isn't available for this account", not "PIN is blank".
    # Hashed with the same PBKDF2 helper as password_hash (app/core/
    # security.py's hash_password/verify_password work on any string),
    # never stored or compared in plaintext.
    pin_hash = Column(String(512), nullable=True)
    pin_set_at = Column(UtcDateTime, nullable=True)
    # A one-time code an administrator generates for a user who forgot
    # their password and cannot reach one in person (UserService.
    # generate_password_reset_code / AuthService.reset_password_with_code).
    # Hashed the same way as a password - this is a credential, even
    # though it is short-lived and single-use.
    password_reset_code_hash = Column(String(512), nullable=True)
    password_reset_code_expires_at = Column(UtcDateTime, nullable=True)
    role_id = Column(String(36), ForeignKey("roles.id"), nullable=True)

    role = relationship("Role", back_populates="users")

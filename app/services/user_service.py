"""
User management service layer (problemstatement.md #6, #39).

Lets an admin create login accounts for any of the six business roles —
multiple users can share a role, matching how a real pump has several
attendants, possibly several accountants, etc. Accounts are never
deleted: deactivate/lock/unlock instead, all audit-logged, matching the
project's rule against destroying historical/security data.
"""

from datetime import datetime, timedelta, timezone
from typing import List

from app.core.constants import PASSWORD_RESET_CODE_LENGTH, PASSWORD_RESET_CODE_VALID_MINUTES, Permission
from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError, WeakPasswordError
from app.core.permissions import require_permission
from app.core.security import (
    generate_numeric_code,
    hash_password,
    validate_password_strength,
    validate_pin_strength,
    verify_password,
)
from app.models.user import User
from app.schemas.user import UserCreate


def _as_aware_utc(value: datetime) -> datetime:
    """SQLite drops tzinfo on round-trip; treat naive values as UTC -
    the same helper AuthService keeps for the same reason."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


# Generic, deliberately identical whether the username doesn't exist, the
# code is wrong, or the code has expired - the same anti-enumeration
# reasoning AuthService.authenticate already applies to login itself:
# distinguishing these cases would let this recovery path be used to
# probe which usernames exist.
_INVALID_RESET_CODE_MESSAGE = "That reset code isn't valid or has expired. Please ask an administrator for a new one."


class UserService:
    def __init__(self, user_repo, role_repo, audit_repo, auth_service):
        self._user_repo = user_repo
        self._role_repo = role_repo
        self._audit_repo = audit_repo
        self._auth_service = auth_service

    @require_permission(Permission.USER_MANAGE.value)
    def create_user(self, actor_user_id: str, data: UserCreate) -> User:
        if self._user_repo.get_by_username(data.username):
            raise ConflictError(f"Username {data.username!r} is already taken")
        if self._user_repo.get_by_email(data.email):
            raise ConflictError(f"Email {data.email!r} is already registered")

        role = self._role_repo.get_by_id(data.role_id)
        if not role:
            raise NotFoundError(f"Role not found: {data.role_id}")

        password_errors = validate_password_strength(data.password)
        if password_errors:
            raise WeakPasswordError("; ".join(password_errors))

        user = User(
            username=data.username,
            email=data.email,
            password_hash=hash_password(data.password),
            first_name=data.first_name,
            last_name=data.last_name,
            role_id=data.role_id,
            is_active=True,
            is_locked=False,
            failed_attempts=0,
            # An admin-assigned password is a temporary one from the
            # account holder's point of view - force them to set their
            # own on first login rather than staying on it indefinitely.
            must_change_password=True,
        )
        user = self._user_repo.add(user)
        self._audit_repo.record(
            event_type="user_created",
            actor_id=actor_user_id,
            entity_type="User",
            entity_id=user.id,
            description=f"Created user {data.username} with role {role.name}",
        )
        return user

    @require_permission(Permission.USER_MANAGE.value)
    def list_users(self, actor_user_id: str) -> List[User]:
        return self._user_repo.list_all()

    @require_permission(Permission.USER_MANAGE.value)
    def set_user_active(self, actor_user_id: str, user_id: str, is_active: bool, reason: str) -> User:
        if not reason or not reason.strip():
            raise ValueError("A reason is required to activate/deactivate a user")

        user = self._get_user_or_raise(user_id)
        old_value = "active" if user.is_active else "inactive"
        user.is_active = is_active
        user = self._user_repo.update(user)
        self._audit_repo.record(
            event_type="user_status_changed",
            actor_id=actor_user_id,
            entity_type="User",
            entity_id=user.id,
            description=reason.strip(),
            old_value=old_value,
            new_value="active" if is_active else "inactive",
        )
        return user

    @require_permission(Permission.USER_MANAGE.value)
    def unlock_user(self, actor_user_id: str, user_id: str, reason: str) -> User:
        if not reason or not reason.strip():
            raise ValueError("A reason is required to unlock a user")

        user = self._get_user_or_raise(user_id)
        if not user.is_locked:
            raise ConflictError("This user is not locked")

        user.is_locked = False
        user.failed_attempts = 0
        user = self._user_repo.update(user)
        self._audit_repo.record(
            event_type="user_unlocked",
            actor_id=actor_user_id,
            entity_type="User",
            entity_id=user.id,
            description=reason.strip(),
        )
        return user

    @require_permission(Permission.USER_MANAGE.value)
    def change_user_role(self, actor_user_id: str, user_id: str, role_id: str, reason: str) -> User:
        if not reason or not reason.strip():
            raise ValueError("A reason is required to change a user's role")

        user = self._get_user_or_raise(user_id)
        role = self._role_repo.get_by_id(role_id)
        if not role:
            raise NotFoundError(f"Role not found: {role_id}")

        old_role_name = user.role.name if user.role else None
        user.role_id = role_id
        user = self._user_repo.update(user)
        self._audit_repo.record(
            event_type="user_role_changed",
            actor_id=actor_user_id,
            entity_type="User",
            entity_id=user.id,
            description=reason.strip(),
            old_value=old_role_name,
            new_value=role.name,
        )
        return user

    @require_permission(Permission.USER_MANAGE.value)
    def reset_password(self, actor_user_id: str, user_id: str, new_password: str, reason: str) -> User:
        """Admin-initiated reset, e.g. because a user forgot their
        password and is locked out with no self-service recovery path.
        Sets must_change_password so the temporary password an admin
        just typed doesn't become permanent by default."""
        if not reason or not reason.strip():
            raise ValueError("A reason is required to reset a user's password")

        password_errors = validate_password_strength(new_password)
        if password_errors:
            raise WeakPasswordError("; ".join(password_errors))

        user = self._get_user_or_raise(user_id)
        user.password_hash = hash_password(new_password)
        user.must_change_password = True
        user = self._user_repo.update(user)
        self._audit_repo.record(
            event_type="user_password_reset",
            actor_id=actor_user_id,
            entity_type="User",
            entity_id=user.id,
            description=reason.strip(),
        )
        return user

    def change_own_password(self, actor_user_id: str, current_password: str, new_password: str) -> User:
        """Self-service password change - any authenticated user may
        change their own password, no USER_MANAGE permission required.
        Used both for the forced first-login rotation and for a
        voluntary later change."""
        user = self._get_user_or_raise(actor_user_id)
        if not verify_password(current_password, user.password_hash):
            raise AuthenticationError("Current password is incorrect")

        password_errors = validate_password_strength(new_password)
        if password_errors:
            raise WeakPasswordError("; ".join(password_errors))

        user.password_hash = hash_password(new_password)
        user.must_change_password = False
        user = self._user_repo.update(user)
        self._audit_repo.record(
            event_type="user_password_changed",
            actor_id=actor_user_id,
            entity_type="User",
            entity_id=user.id,
            description="Self-service password change",
        )
        return user

    def set_own_pin(self, actor_user_id: str, current_password: str, pin: str) -> User:
        """Self-service: set or change the calling user's own quick-
        sign-in PIN (AuthService.authenticate_with_pin uses it).

        Requires re-entering the current password first, the same
        re-authentication change_own_password already requires - proving
        who is at the keyboard right now, not just trusting that this
        session is still the same person who logged in, matters more
        here than usual: this action is what turns a short PIN into a
        second way to sign in as this account at all.
        """
        user = self._get_user_or_raise(actor_user_id)
        if not verify_password(current_password, user.password_hash):
            raise AuthenticationError("Current password is incorrect")

        pin_errors = validate_pin_strength(pin)
        if pin_errors:
            raise WeakPasswordError("; ".join(pin_errors))

        user.pin_hash = hash_password(pin)
        user.pin_set_at = datetime.now(timezone.utc)
        user = self._user_repo.update(user)
        self._audit_repo.record(
            event_type="user_pin_set",
            actor_id=actor_user_id,
            entity_type="User",
            entity_id=user.id,
            description="Self-service quick-sign-in PIN set",
        )
        return user

    @require_permission(Permission.USER_MANAGE.value)
    def generate_password_reset_code(self, actor_user_id: str, user_id: str, reason: str) -> str:
        """Admin-initiated recovery for a user who forgot their password
        and has no one to reset it in person right now (e.g. a night
        shift with no admin on site). Returns the plaintext code - the
        only time it ever exists outside a hash - for the admin to relay
        to the user out of band (read aloud, written down); only its
        hash is stored, and it expires and is single-use (see
        reset_password_with_code).
        """
        if not reason or not reason.strip():
            raise ValueError("A reason is required to generate a password reset code")

        user = self._get_user_or_raise(user_id)
        code = generate_numeric_code(PASSWORD_RESET_CODE_LENGTH)
        user.password_reset_code_hash = hash_password(code)
        user.password_reset_code_expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=PASSWORD_RESET_CODE_VALID_MINUTES
        )
        self._user_repo.update(user)
        self._audit_repo.record(
            event_type="user_password_reset_code_generated",
            actor_id=actor_user_id,
            entity_type="User",
            entity_id=user.id,
            description=reason.strip(),
        )
        return code

    def reset_password_with_code(self, username: str, code: str, new_password: str) -> None:
        """Self-service completion of the admin-generated reset code
        above - reached from the login screen by someone who is, by
        definition, not authenticated yet, so this takes no actor_user_id
        and needs no permission check. Every failure path returns the
        exact same generic message (see _INVALID_RESET_CODE_MESSAGE);
        only success is distinguishable from the outside.
        """
        user = self._user_repo.get_by_username(username)
        if user is None or user.password_reset_code_hash is None:
            self._audit_repo.record(
                event_type="password_reset_code_rejected",
                description=f"Reset code attempted for unknown or code-less account: {username}",
            )
            raise AuthenticationError(_INVALID_RESET_CODE_MESSAGE)

        expired = (
            user.password_reset_code_expires_at is None
            or _as_aware_utc(user.password_reset_code_expires_at) < datetime.now(timezone.utc)
        )
        if expired or not verify_password(code, user.password_reset_code_hash):
            self._audit_repo.record(
                event_type="password_reset_code_rejected",
                actor_id=user.id,
                description="Wrong or expired reset code",
            )
            raise AuthenticationError(_INVALID_RESET_CODE_MESSAGE)

        password_errors = validate_password_strength(new_password)
        if password_errors:
            raise WeakPasswordError("; ".join(password_errors))

        user.password_hash = hash_password(new_password)
        user.must_change_password = False
        # Single-use: a code that already worked once must not work again.
        user.password_reset_code_hash = None
        user.password_reset_code_expires_at = None
        self._user_repo.update(user)
        self._audit_repo.record(
            event_type="password_reset_via_code",
            actor_id=user.id,
            entity_type="User",
            entity_id=user.id,
            description="Password reset via one-time administrator-issued code",
        )

    def _get_user_or_raise(self, user_id: str) -> User:
        user = self._user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(f"User not found: {user_id}")
        return user
